#!/usr/bin/env python3
"""Qt app for right-hand servo testing (5 channels, manual 0..180° control)."""

from __future__ import annotations

import glob
import json
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import serial
import serial.tools.list_ports
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSlider,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


SERVO_MAX_DEG = 180
SERVO_ORDER = [
    ("S1", "THUMB", "9"),
    ("S2", "INDEX", "10"),
    ("S3", "MIDDLE", "11"),
    ("S4", "RING", "12"),
    ("S5", "PINKY", "A0"),
]


def clamp_angle(value: int) -> int:
    return max(0, min(SERVO_MAX_DEG, int(value)))


@dataclass
class ServoState:
    sid: str
    name: str
    pin: str
    angle: int = 0
    power_on: bool = True
    test_running: bool = False


class GripperWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Правая рука: ручной контроль сервоприводов")
        self.setMinimumSize(1100, 680)

        self.ser: serial.Serial | None = None
        self._is_connected = False
        self.states = {
            sid: ServoState(sid=sid, name=name, pin=pin)
            for sid, name, pin in SERVO_ORDER
        }
        self.ui = {}

        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self.poll_serial)
        self._poll_timer.start(40)

        self._build_ui()
        self.refresh_ports()
        self.detect_arduino_brain()

    def _build_ui(self):
        root = QWidget(self)
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)

        serial_box = QGroupBox("Serial / Arduino")
        serial_layout = QGridLayout(serial_box)
        self.port_cb = QComboBox()
        self.baud_cb = QComboBox()
        self.baud_cb.addItems(["9600", "57600", "115200"])
        self.baud_cb.setCurrentText("115200")
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.refresh_ports)
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self.toggle_connection)
        self.status_lbl = QLabel("Disconnected")
        serial_layout.addWidget(QLabel("Port"), 0, 0)
        serial_layout.addWidget(self.port_cb, 0, 1)
        serial_layout.addWidget(self.refresh_btn, 0, 2)
        serial_layout.addWidget(QLabel("Baud"), 1, 0)
        serial_layout.addWidget(self.baud_cb, 1, 1)
        serial_layout.addWidget(self.connect_btn, 1, 2)
        serial_layout.addWidget(QLabel("Status"), 2, 0)
        serial_layout.addWidget(self.status_lbl, 2, 1, 1, 2)
        layout.addWidget(serial_box)

        fw_box = QGroupBox("Arduino UNO / Firmware")
        fw_layout = QGridLayout(fw_box)
        self.brain_lbl = QLabel("Unknown board")
        self.fqbn_cb = QComboBox()
        self.fqbn_cb.addItems(["arduino:avr:uno", "arduino:avr:nano"])
        self.fqbn_cb.setCurrentText("arduino:avr:uno")
        self.sketch_path_lbl = QLabel(
            str(Path(__file__).resolve().parent / "arduino_dual_servo" / "arduino_dual_servo.ino")
        )
        self.detect_btn = QPushButton("Auto detect board")
        self.detect_btn.clicked.connect(self.detect_arduino_brain)
        self.upload_btn = QPushButton("Compile + Upload")
        self.upload_btn.clicked.connect(self.upload_firmware)
        fw_layout.addWidget(QLabel("Board"), 0, 0)
        fw_layout.addWidget(self.brain_lbl, 0, 1, 1, 2)
        fw_layout.addWidget(QLabel("FQBN"), 1, 0)
        fw_layout.addWidget(self.fqbn_cb, 1, 1, 1, 2)
        fw_layout.addWidget(QLabel("Sketch"), 2, 0)
        fw_layout.addWidget(self.sketch_path_lbl, 2, 1, 1, 2)
        fw_layout.addWidget(self.detect_btn, 3, 1)
        fw_layout.addWidget(self.upload_btn, 3, 2)
        layout.addWidget(fw_box)

        ctrl_box = QGroupBox("Правая рука (ручное управление 0..180°)")
        ctrl_layout = QVBoxLayout(ctrl_box)
        top_row = QHBoxLayout()
        top_row.addWidget(QLabel("Пины: S1=9, S2=10, S3=11, S4=12, S5=A0"))
        top_row.addStretch()
        self.all_home_btn = QPushButton("ALL HOME 0°")
        self.all_home_btn.clicked.connect(self.home_all)
        top_row.addWidget(self.all_home_btn)
        self.status_btn = QPushButton("STATUS")
        self.status_btn.clicked.connect(lambda: self.send_command("STATUS"))
        top_row.addWidget(self.status_btn)
        ctrl_layout.addLayout(top_row)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        for row, (sid, _name, _pin) in enumerate(SERVO_ORDER):
            self._build_servo_controls(grid, sid, row)
        ctrl_layout.addLayout(grid)
        layout.addWidget(ctrl_box)

        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        layout.addWidget(self.log_view, 1)

    def _build_servo_controls(self, grid: QGridLayout, sid: str, row: int):
        st = self.states[sid]
        title = QLabel(f"{st.name} ({sid})")
        pin_lbl = QLabel(f"PIN {st.pin}")
        pin_lbl.setStyleSheet("color:#777;")

        angle_lbl = QLabel("0°")
        angle_lbl.setFixedWidth(42)
        angle_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        angle_lbl.setStyleSheet("font-weight:700;color:#1aa260;")

        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(0, SERVO_MAX_DEG)
        slider.setValue(0)
        slider.valueChanged.connect(
            lambda v, s=sid: self.set_servo_angle(s, v, from_slider=True)
        )

        power_btn = QPushButton("POWER ON")
        power_btn.setCheckable(True)
        power_btn.setChecked(True)
        power_btn.clicked.connect(lambda _=False, s=sid: self.toggle_power(s))

        btn0 = QPushButton("0")
        btn0.setFixedWidth(36)
        btn0.clicked.connect(lambda _=False, s=sid: self.set_servo_angle(s, 0))

        btn90 = QPushButton("90")
        btn90.setFixedWidth(36)
        btn90.clicked.connect(lambda _=False, s=sid: self.set_servo_angle(s, 90))

        btn180 = QPushButton("180")
        btn180.setFixedWidth(40)
        btn180.clicked.connect(lambda _=False, s=sid: self.set_servo_angle(s, 180))

        btn_sweep = QPushButton("SWEEP")
        btn_sweep.setFixedWidth(64)
        btn_sweep.clicked.connect(lambda _=False, s=sid: self.run_range_test(s))

        grid.addWidget(title, row, 0)
        grid.addWidget(pin_lbl, row, 1)
        grid.addWidget(slider, row, 2)
        grid.addWidget(angle_lbl, row, 3)
        grid.addWidget(power_btn, row, 4)
        grid.addWidget(btn0, row, 5)
        grid.addWidget(btn90, row, 6)
        grid.addWidget(btn180, row, 7)
        grid.addWidget(btn_sweep, row, 8)

        self.ui[sid] = {
            "slider": slider,
            "angle_lbl": angle_lbl,
            "power_btn": power_btn,
        }

    def log(self, text: str):
        ts = time.strftime("%H:%M:%S")
        self.log_view.append(f"[{ts}] {text}")

    def list_serial_ports(self) -> list[str]:
        detected = [p.device for p in serial.tools.list_ports.comports() if p.device]
        for pattern in ("/dev/ttyUSB*", "/dev/ttyACM*"):
            for dev in glob.glob(pattern):
                if dev not in detected:
                    detected.append(dev)
        usb_like = [d for d in detected if ("/dev/ttyUSB" in d or "/dev/ttyACM" in d)]
        return sorted(usb_like) if usb_like else sorted(detected)

    def refresh_ports(self):
        current = self.port_cb.currentText()
        ports = self.list_serial_ports()
        self.port_cb.clear()
        self.port_cb.addItems(ports if ports else [""])
        if current in ports:
            self.port_cb.setCurrentText(current)
        elif ports:
            self.port_cb.setCurrentIndex(0)
            self.log(f"Auto port selected: {self.port_cb.currentText()}")

    def detect_arduino_brain(self):
        self.refresh_ports()
        port = self.port_cb.currentText().strip()
        if not port:
            self.brain_lbl.setText("No serial port")
            return
        info = self.detect_board_via_arduino_cli(port) or {"name": "n/a", "fqbn": ""}
        fqbn = info.get("fqbn", "")
        self.brain_lbl.setText(info.get("name", "n/a"))
        if fqbn:
            idx = self.fqbn_cb.findText(fqbn)
            if idx >= 0:
                self.fqbn_cb.setCurrentIndex(idx)
        self.log(f"Board detected: {info.get('name', 'n/a')} ({fqbn or 'no fqbn'})")

    def detect_board_via_arduino_cli(self, port: str) -> dict | None:
        cli = shutil.which("arduino-cli")
        if not cli:
            return None
        try:
            res = subprocess.run(
                [cli, "board", "list", "--format", "json"],
                capture_output=True,
                text=True,
                timeout=8,
                check=True,
            )
            data = json.loads(res.stdout or "{}")
            for item in data.get("detected_ports", []):
                if item.get("port", {}).get("address", "") != port:
                    continue
                matches = item.get("matching_boards", [])
                if matches:
                    return {"name": matches[0].get("name", "n/a"), "fqbn": matches[0].get("fqbn", "")}
                return {"name": "n/a", "fqbn": ""}
        except Exception:
            return None
        return None

    def upload_firmware(self):
        cli = shutil.which("arduino-cli")
        if not cli:
            self.log("Install arduino-cli first")
            return
        port = self.port_cb.currentText().strip()
        if not port:
            self.log("No port selected for upload")
            return
        fqbn = self.fqbn_cb.currentText().strip()
        if not fqbn:
            self.log("FQBN is empty")
            return
        sketch_dir = str((Path(__file__).resolve().parent / "arduino_dual_servo"))

        if self._is_connected:
            self.disconnect_serial()
            time.sleep(0.2)

        self.log(f"Compile: {sketch_dir} [{fqbn}]")
        try:
            subprocess.run(
                [cli, "compile", "--fqbn", fqbn, sketch_dir],
                check=True,
                capture_output=True,
                text=True,
                timeout=180,
            )
            self.log(f"Upload to {port}")
            subprocess.run(
                [cli, "upload", "-p", port, "--fqbn", fqbn, sketch_dir],
                check=True,
                capture_output=True,
                text=True,
                timeout=180,
            )
            self.log("Upload complete")
        except subprocess.CalledProcessError as exc:
            self.log("Upload failed")
            if exc.stderr:
                self.log(exc.stderr.strip().splitlines()[-1])
            return
        except Exception as exc:
            self.log(f"Upload error: {exc}")
            return
        QTimer.singleShot(1500, self.connect_serial)

    def toggle_connection(self):
        if self._is_connected:
            self.disconnect_serial()
        else:
            self.connect_serial()

    def connect_serial(self):
        port = self.port_cb.currentText().strip()
        if not port:
            self.log("No serial port selected")
            return
        baud = int(self.baud_cb.currentText())
        try:
            self.ser = serial.Serial(port=port, baudrate=baud, timeout=0.05)
            self._is_connected = True
            self.connect_btn.setText("Disconnect")
            self.status_lbl.setText(f"Connected: {port} @ {baud}")
            self.log(f"Connected to {port} ({baud})")
            QTimer.singleShot(1700, lambda: self.send_command("HELLO"))
            QTimer.singleShot(1900, lambda: self.send_command("STATUS"))
            QTimer.singleShot(2100, self.home_all)
        except Exception as exc:
            self.log(f"Connection failed: {exc}")

    def disconnect_serial(self):
        try:
            if self.ser and self.ser.is_open:
                self.ser.close()
        except Exception:
            pass
        self.ser = None
        self._is_connected = False
        self.connect_btn.setText("Connect")
        self.status_lbl.setText("Disconnected")
        self.log("Disconnected")

    def send_command(self, cmd: str):
        if not self.ser or not self.ser.is_open:
            return
        try:
            self.ser.write((cmd + "\n").encode("utf-8"))
            self.log(f"-> {cmd}")
        except Exception as exc:
            self.log(f"Send failed: {exc}")
            self.disconnect_serial()

    def send_servo(self, sid: str, action: str, arg1: str = ""):
        parts = ["SERVO", sid, action]
        if arg1 != "":
            parts.append(arg1)
        self.send_command(":".join(parts))

    def poll_serial(self):
        if not self.ser or not self.ser.is_open:
            return
        try:
            while self.ser.in_waiting:
                line = self.ser.readline().decode("utf-8", "replace").strip()
                if not line:
                    continue
                self.log(f"<- {line}")
                self.handle_device_line(line)
        except Exception as exc:
            self.log(f"Read failed: {exc}")
            self.disconnect_serial()

    def handle_device_line(self, line: str):
        if not line.startswith("STATE:"):
            return
        # Format: STATE:S1:PIN=9;ANGLE=0;POWER=1
        parts = line.split(":", 2)
        if len(parts) != 3:
            return
        sid = parts[1].strip().upper()
        st = self.states.get(sid)
        if not st:
            return

        data = {}
        for item in parts[2].split(";"):
            if "=" not in item:
                continue
            key, value = item.split("=", 1)
            data[key.strip().upper()] = value.strip()

        angle = data.get("ANGLE")
        power = data.get("POWER")
        pin = data.get("PIN")
        if angle and angle.lstrip("-").isdigit():
            st.angle = clamp_angle(int(angle))
        if power in {"0", "1"}:
            st.power_on = (power == "1")
        if pin:
            st.pin = pin
        self.sync_ui_state(sid)

    def sync_ui_state(self, sid: str):
        st = self.states[sid]
        ui = self.ui[sid]

        ui["slider"].blockSignals(True)
        ui["slider"].setValue(st.angle)
        ui["slider"].blockSignals(False)

        ui["angle_lbl"].setText(f"{st.angle}°")
        ui["power_btn"].blockSignals(True)
        ui["power_btn"].setChecked(st.power_on)
        ui["power_btn"].setText("POWER ON" if st.power_on else "POWER OFF")
        ui["power_btn"].blockSignals(False)

    def toggle_power(self, sid: str):
        st = self.states[sid]
        st.power_on = self.ui[sid]["power_btn"].isChecked()
        self.ui[sid]["power_btn"].setText("POWER ON" if st.power_on else "POWER OFF")
        self.send_servo(sid, "POWER", "ON" if st.power_on else "OFF")

    def set_servo_angle(self, sid: str, angle: int, from_slider: bool = False):
        st = self.states[sid]
        st.angle = clamp_angle(angle)
        self.sync_ui_state(sid)
        self.send_servo(sid, "SET", str(st.angle))
        if not from_slider:
            self.log(f"{sid} -> {st.angle}°")

    def home_all(self):
        self.send_command("SERVO:ALL:HOME")
        for sid in self.states:
            self.states[sid].angle = 0
            self.sync_ui_state(sid)
        self.log("All servos -> 0°")

    def run_range_test(self, sid: str):
        st = self.states[sid]
        if st.test_running:
            self.log(f"{sid}: test already running")
            return
        if not st.power_on:
            self.log(f"{sid}: power is OFF")
            return
        st.test_running = True
        self.log(f"{sid}: test 0° -> 180° -> 0°")
        self.set_servo_angle(sid, 0)
        QTimer.singleShot(650, lambda s=sid: self.set_servo_angle(s, 180))
        QTimer.singleShot(1300, lambda s=sid: self._finish_test_home(s))

    def _finish_test_home(self, sid: str):
        self.set_servo_angle(sid, 0)
        self.states[sid].test_running = False

    def closeEvent(self, event):
        self.disconnect_serial()
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    window = GripperWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
