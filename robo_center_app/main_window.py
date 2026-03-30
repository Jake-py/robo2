"""Main application window for Robo Neural Command."""

import json
import os
import sys
import time

import requests
import serial.tools.list_ports
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QImage, QPixmap, QTextCursor
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QSlider,
    QSplitter,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .brain import RobotBrain
from .theme import C, SS
from .widgets import Led, RadarWidget
from .workers import ArduinoWorker, LocalYoloEngine, SSHWorker, YoloStream


class RoboNeural(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("⬡  ROBO NEURAL COMMAND")
        self.setMinimumSize(1500, 920)
        self.setStyleSheet(SS)

        self.ssh = SSHWorker()
        self.yolo = YoloStream()
        self.ard = ArduinoWorker()
        self.local_ai = LocalYoloEngine()

        self.ssh.out.connect(self._ssh_out)
        self.ssh.status.connect(self._ssh_status)
        self.ssh.server_info.connect(self._ssh_server_info)
        self.yolo.frame.connect(self._on_frame)
        self.yolo.fps_sig.connect(self._on_fps)
        self.yolo.err.connect(lambda e: self._log(e, C["red"]))
        self.ard.rx.connect(self._ard_rx)
        self.ard.status.connect(self._ard_status)

        self.brain = RobotBrain(self._brain_cmd)

        self._fps = 0.0
        self._latency = 0.0
        self._det_count = 0
        self._last_ping_ok = None
        self._connected_server_ip = ""
        self._connected_server_host = ""
        self._selected_photo = ""
        self._photo_result_path = ""
        self._ai_backend = "remote"

        self._build_ui()
        self._ai_backend_changed(self.ai_backend_cb.currentText())
        self._refresh_ports()
        self._update_photo_target()

        self._ping_timer = QTimer(self)
        self._ping_timer.timeout.connect(self._ping)
        self._ping_timer.start(4000)
        self._ping()

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        vbox = QVBoxLayout(root)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)
        vbox.addWidget(self._topbar())

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(1)
        splitter.addWidget(self._left_panel())
        splitter.addWidget(self._center_panel())
        splitter.addWidget(self._right_panel())
        splitter.setSizes([300, 820, 380])
        vbox.addWidget(splitter, 1)
        vbox.addWidget(self._statusbar())

    def _topbar(self):
        bar = QFrame()
        bar.setFixedHeight(46)
        bar.setStyleSheet(
            f"QFrame{{background:{C['deep']};border-bottom:1px solid {C['border']};}}"
        )
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 0, 16, 0)

        title = QLabel("⬡  ROBO NEURAL COMMAND")
        title.setStyleSheet(
            f"color:{C['cyan']};font-size:13px;font-weight:bold;letter-spacing:5px;"
        )
        layout.addWidget(title)
        layout.addStretch()

        layout.addWidget(self._label("SERVER", 9))
        self.ip_in = QLineEdit("10.83.123.180")
        self.ip_in.setFixedWidth(145)
        self.port_in = QLineEdit("8000")
        self.port_in.setFixedWidth(55)
        layout.addWidget(self.ip_in)
        layout.addWidget(self.port_in)

        self.btn_conn = self._btn("CONNECT", C["blue"])
        self.btn_conn.clicked.connect(self._ping)
        layout.addWidget(self.btn_conn)

        self.srv_led = Led(10)
        self.srv_lbl = QLabel("OFFLINE")
        self.srv_lbl.setStyleSheet(
            f"color:{C['text2']};font-size:9px;letter-spacing:3px;"
        )
        layout.addWidget(self.srv_led)
        layout.addWidget(self.srv_lbl)
        return bar

    def _left_panel(self):
        widget = QWidget()
        widget.setStyleSheet(
            f"QWidget{{background:{C['deep']};border-right:1px solid {C['border']};}}"
        )
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        ssh_box = QGroupBox("SSH TERMINAL")
        ssh_layout = QVBoxLayout(ssh_box)
        self.ssh_enable = QCheckBox("Включить SSH терминал")
        self.ssh_enable.stateChanged.connect(lambda state: self.ssh_panel.setVisible(state > 0))
        ssh_layout.addWidget(self.ssh_enable)

        self.ssh_panel = QWidget()
        self.ssh_panel.setVisible(False)
        panel_layout = QVBoxLayout(self.ssh_panel)
        panel_layout.setContentsMargins(0, 4, 0, 0)
        panel_layout.setSpacing(5)
        for label, attr, placeholder, is_password in [
            ("USER", "ssh_user", "username", False),
            ("PASS", "ssh_pass", "••••••••", True),
            ("PORT", "ssh_port_in", "22", False),
        ]:
            row = QHBoxLayout()
            row.addWidget(self._label(label, 9, fixed=48))
            line_edit = QLineEdit()
            line_edit.setPlaceholderText(placeholder)
            if is_password:
                line_edit.setEchoMode(QLineEdit.EchoMode.Password)
            if label == "PORT":
                line_edit.setText("22")
                line_edit.setFixedWidth(55)
            elif label == "USER":
                line_edit.setText("hello-my-red-god")
            setattr(self, attr, line_edit)
            row.addWidget(line_edit)
            panel_layout.addLayout(row)

        buttons_row = QHBoxLayout()
        self.btn_ssh = self._btn("CONNECT SSH")
        self.btn_ssh.clicked.connect(self._ssh_connect)
        buttons_row.addWidget(self.btn_ssh)
        self.ssh_led = Led(8)
        buttons_row.addWidget(self.ssh_led)
        self.ssh_lbl = QLabel("DISCONNECTED")
        self.ssh_lbl.setStyleSheet(f"color:{C['text2']};font-size:9px;")
        buttons_row.addWidget(self.ssh_lbl)
        buttons_row.addStretch()
        panel_layout.addLayout(buttons_row)
        ssh_layout.addWidget(self.ssh_panel)
        layout.addWidget(ssh_box)

        ard_box = QGroupBox("ARDUINO / ESP DEVICES")
        ard_layout = QVBoxLayout(ard_box)
        ard_layout.setSpacing(5)

        row = QHBoxLayout()
        row.addWidget(self._label("DEVICE", 9, fixed=52))
        self.ard_dev = QComboBox()
        self.ard_dev.addItems(["Arduino Uno", "Arduino Nano", "ESP32", "ESP32-CAM", "ESP8266"])
        row.addWidget(self.ard_dev)
        ard_layout.addLayout(row)

        usb_lbl = QLabel("── USB SERIAL ──")
        usb_lbl.setStyleSheet(
            f"color:{C['text3']};font-size:9px;letter-spacing:2px;margin-top:4px;"
        )
        ard_layout.addWidget(usb_lbl)

        row = QHBoxLayout()
        row.addWidget(self._label("PORT", 9, fixed=36))
        self.ard_port = QComboBox()
        row.addWidget(self.ard_port)
        self.btn_ref = self._btn("↻")
        self.btn_ref.setFixedWidth(28)
        self.btn_ref.clicked.connect(self._refresh_ports)
        row.addWidget(self.btn_ref)
        ard_layout.addLayout(row)

        row = QHBoxLayout()
        row.addWidget(self._label("BAUD", 9, fixed=36))
        self.ard_baud = QComboBox()
        self.ard_baud.addItems(["9600", "57600", "115200", "230400"])
        self.ard_baud.setCurrentText("115200")
        row.addWidget(self.ard_baud)
        ard_layout.addLayout(row)

        wifi_lbl = QLabel("── WIFI HTTP ──")
        wifi_lbl.setStyleSheet(
            f"color:{C['text3']};font-size:9px;letter-spacing:2px;margin-top:4px;"
        )
        ard_layout.addWidget(wifi_lbl)
        self.wifi_en = QCheckBox("ESP WiFi режим")
        ard_layout.addWidget(self.wifi_en)
        row = QHBoxLayout()
        row.addWidget(self._label("IP", 9, fixed=20))
        self.esp_ip = QLineEdit("192.168.1.100")
        row.addWidget(self.esp_ip)
        ard_layout.addLayout(row)

        bt_lbl = QLabel("── BLUETOOTH ──")
        bt_lbl.setStyleSheet(
            f"color:{C['text3']};font-size:9px;letter-spacing:2px;margin-top:4px;"
        )
        ard_layout.addWidget(bt_lbl)
        self.bt_en = QCheckBox("BLE режим")
        ard_layout.addWidget(self.bt_en)
        row = QHBoxLayout()
        row.addWidget(self._label("MAC", 9, fixed=32))
        self.bt_mac = QLineEdit()
        self.bt_mac.setPlaceholderText("XX:XX:XX:XX:XX:XX")
        row.addWidget(self.bt_mac)
        ard_layout.addLayout(row)

        buttons_row = QHBoxLayout()
        self.btn_ard_con = self._btn("CONNECT")
        self.btn_ard_con.clicked.connect(self._ard_connect)
        buttons_row.addWidget(self.btn_ard_con)
        self.btn_ard_dis = self._btn("DISC")
        self.btn_ard_dis.setEnabled(False)
        self.btn_ard_dis.clicked.connect(self._ard_disconnect)
        buttons_row.addWidget(self.btn_ard_dis)
        self.ard_led = Led(8)
        buttons_row.addWidget(self.ard_led)
        self.ard_lbl = QLabel("DISCONNECTED")
        self.ard_lbl.setStyleSheet(f"color:{C['text2']};font-size:9px;")
        buttons_row.addWidget(self.ard_lbl)
        ard_layout.addLayout(buttons_row)
        layout.addWidget(ard_box)

        vis_box = QGroupBox("VISION STREAM")
        vis_layout = QVBoxLayout(vis_box)
        vis_layout.setSpacing(5)
        row = QHBoxLayout()
        row.addWidget(self._label("MODE", 9, fixed=40))
        self.yolo_mode = QComboBox()
        self.yolo_mode.addItems(["detect", "track", "segment"])
        row.addWidget(self.yolo_mode)
        vis_layout.addLayout(row)

        row = QHBoxLayout()
        row.addWidget(self._label("SRC", 9, fixed=30))
        self.cam_src = QLineEdit("0")
        self.cam_src.setPlaceholderText("0 / rtsp://...")
        row.addWidget(self.cam_src)
        vis_layout.addLayout(row)

        row = QHBoxLayout()
        row.addWidget(self._label("CONF", 9, fixed=34))
        self.conf_sl = QSlider(Qt.Orientation.Horizontal)
        self.conf_sl.setRange(10, 90)
        self.conf_sl.setValue(25)
        self.conf_lbl = QLabel("0.25")
        self.conf_lbl.setFixedWidth(34)
        self.conf_sl.valueChanged.connect(lambda value: self.conf_lbl.setText(f"{value / 100:.2f}"))
        row.addWidget(self.conf_sl)
        row.addWidget(self.conf_lbl)
        vis_layout.addLayout(row)

        buttons_row = QHBoxLayout()
        self.btn_cam_start = self._btn("▶ START", C["green_dim"])
        self.btn_cam_start.clicked.connect(self._cam_start)
        buttons_row.addWidget(self.btn_cam_start)
        self.btn_cam_stop = self._btn("■ STOP", C["red"])
        self.btn_cam_stop.clicked.connect(self._cam_stop)
        self.btn_cam_stop.setEnabled(False)
        buttons_row.addWidget(self.btn_cam_stop)
        vis_layout.addLayout(buttons_row)
        layout.addWidget(vis_box)

        ai_box = QGroupBox("AI ENGINE")
        ai_layout = QVBoxLayout(ai_box)
        ai_layout.setSpacing(5)

        row = QHBoxLayout()
        row.addWidget(self._label("BACKEND", 9, fixed=52))
        self.ai_backend_cb = QComboBox()
        self.ai_backend_cb.addItems(["SERVER HTTP", "LOCAL YOLOv11s"])
        self.ai_backend_cb.currentTextChanged.connect(self._ai_backend_changed)
        row.addWidget(self.ai_backend_cb)
        ai_layout.addLayout(row)

        row = QHBoxLayout()
        row.addWidget(self._label("MODEL", 9, fixed=52))
        self.ai_model_in = QLineEdit("yolo11s.pt")
        row.addWidget(self.ai_model_in)
        ai_layout.addLayout(row)

        row = QHBoxLayout()
        row.addWidget(self._label("DEVICE", 9, fixed=52))
        self.ai_device_cb = QComboBox()
        self.ai_device_cb.addItems(["cpu", "cuda:0"])
        row.addWidget(self.ai_device_cb)
        ai_layout.addLayout(row)

        buttons_row = QHBoxLayout()
        self.btn_ai_load = self._btn("LOAD AI", C["green_dim"])
        self.btn_ai_load.clicked.connect(self._ai_load)
        buttons_row.addWidget(self.btn_ai_load)
        self.btn_ai_unload = self._btn("UNLOAD")
        self.btn_ai_unload.clicked.connect(self._ai_unload)
        buttons_row.addWidget(self.btn_ai_unload)
        self.ai_led = Led(8)
        buttons_row.addWidget(self.ai_led)
        self.ai_lbl = QLabel("REMOTE")
        self.ai_lbl.setStyleSheet(f"color:{C['text2']};font-size:9px;")
        buttons_row.addWidget(self.ai_lbl)
        buttons_row.addStretch()
        ai_layout.addLayout(buttons_row)
        layout.addWidget(ai_box)

        layout.addStretch()
        return widget

    def _center_panel(self):
        tabs = QTabWidget()
        tabs.addTab(self._tab_vision(), "VISION")
        tabs.addTab(self._tab_photo(), "PHOTO")
        tabs.addTab(self._tab_ssh(), "TERMINAL")
        tabs.addTab(self._tab_robot(), "ROBOT")
        tabs.addTab(self._tab_arduino(), "ARDUINO")
        return tabs

    def _tab_vision(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        hud = QHBoxLayout()
        self.hud_fps = self._badge("FPS", "0.0", C["cyan"])
        self.hud_lat = self._badge("LAT", "0ms", C["amber"])
        self.hud_obj = self._badge("OBJ", "0", C["green"])
        self.hud_mode = self._badge("MODE", "—", C["purple"])
        for badge in [self.hud_fps, self.hud_lat, self.hud_obj, self.hud_mode]:
            hud.addWidget(badge)
        hud.addStretch()
        layout.addLayout(hud)

        self.vid = QLabel("NO SIGNAL")
        self.vid.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.vid.setMinimumHeight(380)
        self.vid.setStyleSheet(
            f"""
            background:{C['void']};color:{C['text3']};
            border:1px solid {C['border']};
            font-size:20px;letter-spacing:8px;
        """
        )
        layout.addWidget(self.vid, 1)

        self.det_view = QTextEdit()
        self.det_view.setReadOnly(True)
        self.det_view.setMaximumHeight(110)
        self.det_view.setStyleSheet(
            f"""
            background:{C['void']};color:{C['green']};
            border:1px solid {C['border']};font-size:11px;
        """
        )
        layout.addWidget(self.det_view)
        return widget

    def _tab_photo(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        source_box = QGroupBox("PHOTO SOURCE")
        source_layout = QVBoxLayout(source_box)

        path_row = QHBoxLayout()
        path_row.addWidget(self._label("FILE", 9, fixed=34))
        self.photo_path = QLineEdit()
        self.photo_path.setReadOnly(True)
        self.photo_path.setPlaceholderText("Выберите фото для отправки на сервер или YOLO")
        path_row.addWidget(self.photo_path, 1)
        self.btn_photo_pick = self._btn("CHOOSE", C["blue"])
        self.btn_photo_pick.clicked.connect(self._pick_photo)
        path_row.addWidget(self.btn_photo_pick)
        source_layout.addLayout(path_row)

        info_row = QHBoxLayout()
        info_row.addWidget(self._label("TARGET", 9, fixed=48))
        self.photo_target_lbl = QLabel("manual ip")
        self.photo_target_lbl.setStyleSheet(f"color:{C['cyan']};font-weight:bold;")
        info_row.addWidget(self.photo_target_lbl)
        info_row.addStretch()
        self.photo_status_lbl = QLabel("NO PHOTO")
        self.photo_status_lbl.setStyleSheet(f"color:{C['text3']};font-size:10px;")
        info_row.addWidget(self.photo_status_lbl)
        source_layout.addLayout(info_row)

        preview_row = QHBoxLayout()
        self.photo_preview = QLabel("PHOTO PREVIEW")
        self.photo_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.photo_preview.setMinimumSize(320, 220)
        self.photo_preview.setStyleSheet(
            f"background:{C['void']};color:{C['text3']};border:1px solid {C['border']};font-size:16px;letter-spacing:4px;"
        )
        preview_row.addWidget(self.photo_preview, 1)

        self.photo_result_preview = QLabel("RESULT PREVIEW")
        self.photo_result_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.photo_result_preview.setMinimumSize(320, 220)
        self.photo_result_preview.setStyleSheet(
            f"background:{C['void']};color:{C['text3']};border:1px solid {C['border']};font-size:16px;letter-spacing:4px;"
        )
        preview_row.addWidget(self.photo_result_preview, 1)
        source_layout.addLayout(preview_row)
        layout.addWidget(source_box)

        action_box = QGroupBox("SEND / AI")
        action_layout = QVBoxLayout(action_box)

        row = QHBoxLayout()
        row.addWidget(self._label("YOLO", 9, fixed=34))
        self.photo_mode = QComboBox()
        self.photo_mode.addItems(["detect", "track", "segment"])
        row.addWidget(self.photo_mode)
        row.addStretch()
        row.addWidget(self._label("UPLOAD", 9, fixed=48))
        self.photo_upload_path = QLineEdit("/upload")
        self.photo_upload_path.setPlaceholderText("/upload")
        row.addWidget(self.photo_upload_path)
        action_layout.addLayout(row)

        meta_row = QHBoxLayout()
        meta_row.addWidget(self._label("DATA", 9, fixed=34))
        self.photo_meta = QLineEdit()
        self.photo_meta.setPlaceholderText("Доп. данные для ПК сервера: scene=lobby, camera=front")
        meta_row.addWidget(self.photo_meta, 1)
        action_layout.addLayout(meta_row)

        buttons_row = QHBoxLayout()
        self.btn_send_pc = self._btn("SEND TO PC", C["amber"])
        self.btn_send_pc.clicked.connect(self._send_photo_to_pc)
        buttons_row.addWidget(self.btn_send_pc)
        self.btn_send_ai = self._btn("YOLO ANALYZE", C["green_dim"])
        self.btn_send_ai.clicked.connect(self._send_photo_to_ai)
        buttons_row.addWidget(self.btn_send_ai)
        self.btn_send_both = self._btn("SEND BOTH", C["purple"])
        self.btn_send_both.clicked.connect(self._send_photo_both)
        buttons_row.addWidget(self.btn_send_both)
        buttons_row.addStretch()
        action_layout.addLayout(buttons_row)
        layout.addWidget(action_box)

        result_box = QGroupBox("RESULT")
        result_layout = QVBoxLayout(result_box)
        self.photo_result = QTextEdit()
        self.photo_result.setReadOnly(True)
        self.photo_result.setStyleSheet(
            f"background:{C['void']};color:{C['green']};border:1px solid {C['border']};font-size:11px;"
        )
        result_layout.addWidget(self.photo_result)
        layout.addWidget(result_box, 1)
        return widget

    def _tab_ssh(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(6, 6, 6, 6)
        self.ssh_view = QTextEdit()
        self.ssh_view.setReadOnly(True)
        self.ssh_view.setStyleSheet(
            f"background:{C['void']};color:{C['green']};border:1px solid {C['border']};font-size:12px;"
        )
        layout.addWidget(self.ssh_view, 1)
        row = QHBoxLayout()
        self.ssh_prompt_lbl = QLabel("$")
        self.ssh_prompt_lbl.setStyleSheet(f"color:{C['cyan']};font-size:14px;padding:0 4px;")
        self.ssh_in = QLineEdit()
        self.ssh_in.setPlaceholderText("команда SSH...")
        self.ssh_in.returnPressed.connect(self._ssh_send)
        self.btn_ssh_send = self._btn("SEND")
        self.btn_ssh_send.clicked.connect(self._ssh_send)
        row.addWidget(self.ssh_prompt_lbl)
        row.addWidget(self.ssh_in)
        row.addWidget(self.btn_ssh_send)
        layout.addLayout(row)
        return widget

    def _tab_robot(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        link_box = QGroupBox("AI LINK")
        link_layout = QHBoxLayout(link_box)
        link_layout.addWidget(self._label("SOURCE", 9, fixed=52))
        self.ai_source_lbl = QLabel("SERVER HTTP")
        self.ai_source_lbl.setStyleSheet(f"color:{C['cyan']};font-weight:bold;")
        link_layout.addWidget(self.ai_source_lbl)
        link_layout.addStretch()
        self.ai_link_on = QCheckBox("Связать ИИ с роботом")
        self.ai_link_on.stateChanged.connect(self._ai_link_toggle)
        link_layout.addWidget(self.ai_link_on)
        layout.addWidget(link_box)

        ai_box = QGroupBox("AI АВТОНОМНЫЙ МОЗГ")
        ai_layout = QHBoxLayout(ai_box)
        self.ai_on = QCheckBox("ИИ управляет роботом")
        self.ai_on.setStyleSheet(f"color:{C['amber']};font-size:12px;font-weight:bold;")
        self.ai_on.stateChanged.connect(self._ai_toggle)
        ai_layout.addWidget(self.ai_on)
        ai_layout.addStretch()
        ai_layout.addWidget(QLabel("РЕЖИМ:"))
        self.ai_mode_cb = QComboBox()
        self.ai_mode_cb.addItems(["FOLLOW", "PATROL", "AVOID", "GUARD"])
        self.ai_mode_cb.currentTextChanged.connect(self.brain.set_mode)
        ai_layout.addWidget(self.ai_mode_cb)
        ai_layout.addWidget(QLabel("ЦЕЛЬ:"))
        self.ai_target = QComboBox()
        self.ai_target.addItems(["person", "car", "bicycle", "cat", "dog", "bottle"])
        self.ai_target.currentTextChanged.connect(self.brain.set_target)
        ai_layout.addWidget(self.ai_target)
        layout.addWidget(ai_box)

        move_box = QGroupBox("ДВИЖЕНИЕ")
        grid = QGridLayout(move_box)
        grid.setSpacing(6)
        moves = [
            ("↑", 0, 1, "FORWARD"),
            ("←", 1, 0, "LEFT"),
            ("✕", 1, 1, "STOP"),
            ("→", 1, 2, "RIGHT"),
            ("↓", 2, 1, "BACKWARD"),
        ]
        button_style = f"""
            QPushButton{{background:{C['raised']};color:{C['text']};
            border:1px solid {C['border2']};border-radius:2px;
            font-size:20px;min-width:54px;min-height:54px;}}
            QPushButton:hover{{background:{C['blue']};border-color:{C['cyan']};}}
            QPushButton:pressed{{background:{C['cyan']};color:{C['void']};}}
        """
        for label, row, col, cmd in moves:
            button = QPushButton(label)
            button.setStyleSheet(button_style if cmd != "STOP" else button_style.replace(C["text"], C["red"]))
            button.clicked.connect(lambda _checked=False, direction=cmd: self._move(direction))
            grid.addWidget(button, row, col)

        speed_row = QHBoxLayout()
        speed_row.addWidget(self._label("SPEED", 9, fixed=46))
        self.spd_sl = QSlider(Qt.Orientation.Horizontal)
        self.spd_sl.setRange(0, 255)
        self.spd_sl.setValue(130)
        self.spd_lbl = QLabel("130")
        self.spd_lbl.setFixedWidth(32)
        self.spd_sl.valueChanged.connect(lambda value: self.spd_lbl.setText(str(value)))
        speed_row.addWidget(self.spd_sl)
        speed_row.addWidget(self.spd_lbl)
        grid.addLayout(speed_row, 3, 0, 1, 3)
        layout.addWidget(move_box)

        arm_box = QGroupBox("МАНИПУЛЯТОР")
        arm_grid = QGridLayout(arm_box)
        arm_grid.setSpacing(4)
        for i, name in enumerate(["BASE", "SHOULDER", "ELBOW", "WRIST", "GRIPPER"]):
            arm_grid.addWidget(self._label(name, 9, fixed=72), i, 0)
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(0, 180)
            slider.setValue(90)
            value_lbl = QLabel("90°")
            value_lbl.setStyleSheet(f"color:{C['cyan']};")
            value_lbl.setFixedWidth(38)
            slider.valueChanged.connect(
                lambda value, lbl=value_lbl, servo_name=name: (lbl.setText(f"{value}°"), self._servo(servo_name, value))
            )
            arm_grid.addWidget(slider, i, 1)
            arm_grid.addWidget(value_lbl, i, 2)
        layout.addWidget(arm_box)

        layout.addStretch()
        return widget

    def _tab_arduino(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(6, 6, 6, 6)
        self.ard_mon = QTextEdit()
        self.ard_mon.setReadOnly(True)
        self.ard_mon.setStyleSheet(
            f"background:{C['void']};color:{C['amber']};border:1px solid {C['border']};font-size:12px;"
        )
        layout.addWidget(self.ard_mon, 1)
        row = QHBoxLayout()
        self.ard_in = QLineEdit()
        self.ard_in.setPlaceholderText("Команда Arduino (LED:ON, MOTOR:FWD:200...)")
        self.ard_in.returnPressed.connect(self._ard_send_manual)
        row.addWidget(self.ard_in)
        button = self._btn("SEND")
        button.clicked.connect(self._ard_send_manual)
        row.addWidget(button)
        layout.addLayout(row)

        sensor_box = QGroupBox("SENSORS (ARDUINO / ESP32)")
        sensor_grid = QGridLayout(sensor_box)
        self._sensor_labels = {}
        sensors = [
            ("ROBOT", "ROBOT"),
            ("IR", "IR"),
            ("ULTRA", "ULTRA"),
            ("BUMPER", "BUMPER"),
            ("IMU", "IMU"),
            ("TEMP", "TEMP"),
            ("BATTERY", "BATTERY"),
            ("ESP_RSSI", "ESP_RSSI"),
        ]
        for i, (label, key) in enumerate(sensors):
            sensor_grid.addWidget(self._label(label, 9, fixed=72), i, 0)
            value_lbl = QLabel("—")
            value_lbl.setStyleSheet(f"color:{C['cyan']};font-weight:bold;")
            value_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            sensor_grid.addWidget(value_lbl, i, 1)
            self._sensor_labels[key] = value_lbl
        layout.addWidget(sensor_box)

        quick_box = QGroupBox("БЫСТРЫЕ КОМАНДЫ")
        quick_layout = QHBoxLayout(quick_box)
        for cmd in ["LED:ON", "LED:OFF", "RESET", "STATUS", "MOTOR:STOP", "SERVO:CENTER"]:
            quick_button = QPushButton(cmd)
            quick_button.setFixedHeight(26)
            quick_button.setStyleSheet("font-size:9px;letter-spacing:1px;")
            quick_button.clicked.connect(lambda _checked=False, value=cmd: self._ard_quick(value))
            quick_layout.addWidget(quick_button)
        layout.addWidget(quick_box)
        return widget

    def _right_panel(self):
        widget = QWidget()
        widget.setStyleSheet(
            f"QWidget{{background:{C['deep']};border-left:1px solid {C['border']};}}"
        )
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        rad_box = QGroupBox("OBJECT RADAR")
        rad_layout = QVBoxLayout(rad_box)
        self.radar = RadarWidget()
        self.radar.setMinimumHeight(220)
        rad_layout.addWidget(self.radar)
        layout.addWidget(rad_box)

        stats_box = QGroupBox("SYSTEM STATS")
        stats_grid = QGridLayout(stats_box)
        self._stats = {}
        for i, (name, key) in enumerate(
            [
                ("FPS", "fps"),
                ("LATENCY", "latency"),
                ("OBJECTS", "objects"),
                ("TRACKS", "tracks"),
                ("AI MODE", "ai_mode"),
                ("ROBOT", "robot_cmd"),
            ]
        ):
            stats_grid.addWidget(self._label(name, 9, fixed=64), i, 0)
            label = QLabel("—")
            label.setStyleSheet(f"color:{C['cyan']};font-weight:bold;")
            label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            stats_grid.addWidget(label, i, 1)
            self._stats[key] = label
        layout.addWidget(stats_box)

        log_box = QGroupBox("SYSTEM LOG")
        log_layout = QVBoxLayout(log_box)
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setStyleSheet(
            f"background:{C['void']};color:{C['text2']};border:none;font-size:10px;"
        )
        log_layout.addWidget(self.log_view)
        layout.addWidget(log_box, 1)

        return widget

    def _statusbar(self):
        bar = QFrame()
        bar.setFixedHeight(26)
        bar.setStyleSheet(
            f"QFrame{{background:{C['deep']};border-top:1px solid {C['border']};}}"
        )
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(14, 0, 14, 0)
        self.status_lbl = QLabel("СИСТЕМА ИНИЦИАЛИЗИРОВАНА")
        self.status_lbl.setStyleSheet(
            f"color:{C['text2']};font-size:9px;letter-spacing:2px;"
        )
        layout.addWidget(self.status_lbl)
        layout.addStretch()
        version = QLabel("ROBO NEURAL v2.0  ·  YOLO11x  ·  CUDA 12.8  ·  RTX 5070 Ti")
        version.setStyleSheet(f"color:{C['text3']};font-size:9px;")
        layout.addWidget(version)
        return bar

    def _btn(self, text, color=None):
        button = QPushButton(text)
        if color:
            button.setStyleSheet(
                f"""
                QPushButton{{background:{color};color:white;border:none;border-radius:2px;
                padding:5px 12px;font-size:10px;letter-spacing:2px;font-weight:bold;}}
                QPushButton:hover{{filter:brightness(1.2);opacity:0.9;}}
                QPushButton:disabled{{background:{C['border']};color:{C['text3']};}}
            """
            )
        return button

    def _label(self, text, size=12, fixed=None):
        label = QLabel(text)
        label.setStyleSheet(f"color:{C['text2']};font-size:{size}px;letter-spacing:1px;")
        if fixed:
            label.setFixedWidth(fixed)
        return label

    def _badge(self, key, value, color):
        frame = QFrame()
        frame.setStyleSheet(
            f"QFrame{{background:{C['panel']};border:1px solid {C['border']};border-radius:2px;padding:2px 6px;}}"
        )
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(6, 3, 6, 3)
        layout.setSpacing(6)
        k = QLabel(key)
        k.setStyleSheet(f"color:{C['text2']};font-size:9px;letter-spacing:2px;")
        v = QLabel(value)
        v.setStyleSheet(f"color:{color};font-weight:bold;font-size:12px;")
        layout.addWidget(k)
        layout.addWidget(v)
        setattr(self, f"_badge_val_{key}", v)
        return frame

    def _badge_set(self, key, value):
        label = getattr(self, f"_badge_val_{key}", None)
        if label:
            label.setText(value)

    def _log(self, msg, color=None):
        color = color or C["text2"]
        ts = time.strftime("%H:%M:%S")
        self.log_view.append(
            f'<span style="color:{C["text3"]}">[{ts}]</span> '
            f'<span style="color:{color}">{msg}</span>'
        )
        self.status_lbl.setText(msg[:90])

    def _refresh_ports(self):
        self.ard_port.clear()
        ports = [port.device for port in serial.tools.list_ports.comports()]
        self.ard_port.addItems(ports if ports else ["(нет портов)"])

    def _ai_backend_changed(self, text):
        is_local = "LOCAL" in text
        self._ai_backend = "local" if is_local else "remote"
        self.ai_model_in.setEnabled(is_local)
        self.ai_device_cb.setEnabled(is_local)
        self.btn_ai_load.setEnabled(is_local)
        self.btn_ai_unload.setEnabled(is_local)
        if is_local:
            self.ai_source_lbl.setText("LOCAL YOLOv11s")
            if self.local_ai.is_ready:
                self.ai_led.set(C["green"])
                self.ai_lbl.setText("LOCAL READY")
                self.ai_lbl.setStyleSheet(f"color:{C['green']};font-size:9px;")
            else:
                self.ai_led.set(C["amber"], True)
                self.ai_lbl.setText("LOCAL NOT LOADED")
                self.ai_lbl.setStyleSheet(f"color:{C['amber']};font-size:9px;")
        else:
            self.ai_source_lbl.setText("SERVER HTTP")
            self.ai_led.set(C["cyan_dim"])
            self.ai_lbl.setText("REMOTE")
            self.ai_lbl.setStyleSheet(f"color:{C['text2']};font-size:9px;")
        self._log(f"AI backend: {self.ai_source_lbl.text()}", C["cyan"])

    def _ai_load(self):
        model_name = self.ai_model_in.text().strip() or "yolo11s.pt"
        device = self.ai_device_cb.currentText()
        try:
            self.local_ai.load(model_name, device)
            self.ai_led.set(C["green"])
            self.ai_lbl.setText("LOCAL READY")
            self.ai_lbl.setStyleSheet(f"color:{C['green']};font-size:9px;")
            self._log(f"Local AI loaded: {model_name} ({device})", C["green"])
        except Exception as exc:
            self.ai_led.set(C["red"])
            self.ai_lbl.setText("LOCAL ERROR")
            self.ai_lbl.setStyleSheet(f"color:{C['red']};font-size:9px;")
            self._log(f"Local AI load failed: {exc}", C["red"])

    def _ai_unload(self):
        self.local_ai.unload()
        self.ai_led.set(C["amber"], True)
        self.ai_lbl.setText("LOCAL UNLOADED")
        self.ai_lbl.setStyleSheet(f"color:{C['amber']};font-size:9px;")
        self._log("Local AI unloaded", C["amber"])

    def _ai_link_toggle(self, state):
        desired = state > 0
        if self.ai_on.isChecked() != desired:
            self.ai_on.blockSignals(True)
            self.ai_on.setChecked(desired)
            self.ai_on.blockSignals(False)
            self._ai_toggle(2 if desired else 0)

    def _ping(self):
        ip = self.ip_in.text().strip()
        port = self.port_in.text().strip()
        ok = False
        device_name = "?"
        try:
            response = requests.get(f"http://{ip}:{port}/health", timeout=1.5)
            if response.status_code == 200:
                data = response.json()
                ok = True
                device_name = data.get("device", "?")
        except Exception:
            ok = False

        if ok:
            self.srv_led.set(C["green"])
            self.srv_lbl.setText("ONLINE")
            self.srv_lbl.setStyleSheet(f"color:{C['green']};font-size:9px;letter-spacing:3px;")
            if self._last_ping_ok is not True:
                self._log(f"Server OK · {device_name}", C["green"])
        else:
            self.srv_led.set(C["red"])
            self.srv_lbl.setText("OFFLINE")
            self.srv_lbl.setStyleSheet(f"color:{C['red']};font-size:9px;letter-spacing:3px;")
            if self._last_ping_ok is not False:
                self._log("Server offline", C["red"])
        self._last_ping_ok = ok

    def _server_url(self):
        host = self._connected_server_ip or self.ip_in.text().strip()
        return f"http://{host}:{self.port_in.text().strip()}"

    def _ssh_connect(self):
        ip = self.ip_in.text().strip()
        user = self.ssh_user.text().strip()
        pwd = self.ssh_pass.text()
        try:
            port = int(self.ssh_port_in.text().strip() or "22")
        except ValueError:
            self._log("SSH port must be a number", C["red"])
            return
        self._log(f"SSH -> {user}@{ip}:{port}", C["cyan"])
        self.ssh.connect_to_host(ip, user, pwd, port)

    def _ssh_status(self, ok, msg):
        color = C["green"] if ok else C["red"]
        self.ssh_led.set(color, not ok)
        self.ssh_lbl.setText("CONNECTED" if ok else "FAILED")
        self.ssh_lbl.setStyleSheet(f"color:{color};font-size:9px;")
        if not ok:
            self._connected_server_ip = ""
            self._connected_server_host = ""
            self._update_photo_target()
        self._log(msg, color)

    def _ssh_server_info(self, hostname, primary_ip, all_ips):
        self._connected_server_host = hostname
        self._connected_server_ip = primary_ip
        self.ip_in.setText(primary_ip)
        self._update_photo_target()
        self._log(f"SSH server: {hostname} · IP {primary_ip}", C["cyan"])
        if all_ips and all_ips != primary_ip:
            self._log(f"Server IP list: {all_ips}", C["text2"])

    def _ssh_out(self, text):
        self.ssh_view.moveCursor(QTextCursor.MoveOperation.End)
        self.ssh_view.insertPlainText(text)
        self.ssh_view.moveCursor(QTextCursor.MoveOperation.End)

    def _ssh_send(self):
        cmd = self.ssh_in.text().strip()
        if not cmd:
            return
        self.ssh.send(cmd)
        self.ssh_view.append(f'<span style="color:{C["cyan"]}">$ {cmd}</span>')
        self.ssh_in.clear()

    def _cam_start(self):
        src = self.cam_src.text().strip()
        mode = self.yolo_mode.currentText()
        conf = self.conf_sl.value() / 100
        if self._ai_backend == "local" and not self.local_ai.is_ready:
            self._log("Local AI not loaded. Click LOAD AI.", C["red"])
            return
        self.yolo.set_backend(self._ai_backend, self.local_ai)
        self.yolo.start_stream(self._server_url(), src, mode, conf)
        if self.yolo.isRunning():
            self.btn_cam_start.setEnabled(False)
            self.btn_cam_stop.setEnabled(True)
            self._badge_set("MODE", mode.upper())
            self._log(f"Vision start [{mode}] src={src} conf={conf}", C["cyan"])

    def _cam_stop(self):
        self.yolo.stop()
        self.btn_cam_start.setEnabled(True)
        self.btn_cam_stop.setEnabled(False)
        self.vid.setText("NO SIGNAL")
        self.vid.setPixmap(QPixmap())
        self.det_view.clear()
        self._log("Vision stopped", C["amber"])

    def _on_frame(self, image: QImage, detections: list):
        pixmap = QPixmap.fromImage(image).scaled(
            self.vid.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.vid.setPixmap(pixmap)
        self._det_count = len(detections)
        self._badge_set("OBJ", str(self._det_count))
        self._stats["objects"].setText(str(self._det_count))
        track_count = len([d for d in detections if d.get("track_id") is not None])
        self._stats["tracks"].setText(str(track_count))

        self.radar.update_objects(detections)

        if detections:
            lines = []
            for detection in detections:
                tid = detection.get("track_id")
                lines.append(
                    f"  [{detection.get('class_name', '?')}]"
                    + (f" #{tid}" if tid is not None else "")
                    + f"  conf={detection.get('confidence', 0):.2f}"
                )
            self.det_view.setPlainText("\n".join(lines))
        else:
            self.det_view.clear()

        if self.ai_on.isChecked():
            self.brain.process(detections, frame_w=image.width(), frame_h=image.height())

    def _on_fps(self, fps, latency):
        self._fps = fps
        self._latency = latency
        self._badge_set("FPS", f"{fps:.1f}")
        self._badge_set("LAT", f"{latency:.0f}ms")
        self._stats["fps"].setText(f"{fps:.1f}")
        self._stats["latency"].setText(f"{latency:.0f} ms")

    def _ard_connect(self):
        if self.wifi_en.isChecked():
            self._log(f"ESP WiFi mode: {self.esp_ip.text()}", C["amber"])
            self.ard_led.set(C["amber"], True)
            self.ard_lbl.setText("WIFI MODE")
            return
        if self.bt_en.isChecked():
            self._log(f"BLE mode: {self.bt_mac.text()} (async - нужен bleak)", C["purple"])
            self.ard_led.set(C["purple"], True)
            self.ard_lbl.setText("BLE MODE")
            return
        port = self.ard_port.currentText()
        if not port or port == "(нет портов)":
            self._log("No serial ports found", C["red"])
            return
        baud = int(self.ard_baud.currentText())
        self.ard.connect_to_port(port, baud)

    def _ard_disconnect(self):
        self.ard.stop()
        self.ard_led.set(C["text3"])
        self.ard_lbl.setText("DISCONNECTED")
        self.btn_ard_con.setEnabled(True)
        self.btn_ard_dis.setEnabled(False)
        self._log("Arduino disconnected", C["amber"])

    def _ard_status(self, ok, msg):
        color = C["green"] if ok else C["red"]
        self.ard_led.set(color, not ok)
        self.ard_lbl.setText("CONNECTED" if ok else "FAILED")
        self.ard_lbl.setStyleSheet(f"color:{color};font-size:9px;")
        self.btn_ard_con.setEnabled(not ok)
        self.btn_ard_dis.setEnabled(ok)
        self._log(msg, color)

    def _ard_rx(self, data):
        self.ard_mon.append(f'<span style="color:{C["amber"]}">← {data}</span>')
        self._parse_sensor_line(data)

    def _ard_send(self, cmd):
        if self.wifi_en.isChecked():
            try:
                requests.post(
                    f"http://{self.esp_ip.text().strip()}/cmd",
                    json={"cmd": cmd},
                    timeout=0.5,
                )
            except Exception:
                self._log("ESP WiFi command failed", C["red"])
        else:
            self.ard.send(cmd)
        self.ard_mon.append(f'<span style="color:{C["cyan"]}">→ {cmd}</span>')
        self._stats["robot_cmd"].setText(cmd[:24])

    def _ard_send_manual(self):
        cmd = self.ard_in.text().strip()
        if cmd:
            self._ard_send(cmd)
            self.ard_in.clear()

    def _ard_quick(self, cmd):
        self._ard_send(cmd)

    def _move(self, direction):
        speed = self.spd_sl.value()
        self._ard_send(f"MOVE:{direction}:{speed}")
        self._log(f"MOVE {direction} speed={speed}", C["cyan"])

    def _servo(self, name, angle):
        self._ard_send(f"SERVO:{name}:{angle}")

    def _ai_toggle(self, state):
        mode = self.ai_mode_cb.currentText() if state > 0 else "IDLE"
        self.brain.set_mode(mode)
        self._stats["ai_mode"].setText(mode)
        self.ai_link_on.blockSignals(True)
        self.ai_link_on.setChecked(state > 0)
        self.ai_link_on.blockSignals(False)
        self._log(f"AI Brain: {'ON -> ' + mode if state > 0 else 'OFF'}", C["amber"])

    def _brain_cmd(self, cmd):
        self._ard_send(cmd)
        self._log(f"AI CMD: {cmd}", C["purple"])

    def _update_photo_target(self):
        target = self._connected_server_ip or self.ip_in.text().strip() or "manual ip"
        if self._connected_server_host:
            target = f"{target} ({self._connected_server_host})"
        self.photo_target_lbl.setText(target)

    def _parse_sensor_line(self, data):
        if not hasattr(self, "_sensor_labels"):
            return
        raw = data.strip()
        prefixes = ["SENSOR:", "ESP32:", "ESP:"]
        for prefix in prefixes:
            if raw.startswith(prefix):
                rest = raw[len(prefix) :].strip()
                parts = rest.split(":")
                if len(parts) < 2:
                    return
                key = parts[0].strip().upper()
                value = ":".join(parts[1:]).strip()
                if prefix.startswith("ESP") and key == "RSSI":
                    key = "ESP_RSSI"
                self._set_sensor_value(key, value)
                return

    def _set_sensor_value(self, key, value):
        label = self._sensor_labels.get(key)
        if not label:
            return
        label.setText(value)
        if key == "ROBOT":
            on = value.strip().lower() in {"1", "on", "true", "yes", "detected"}
            label.setStyleSheet(f"color:{C['green'] if on else C['red']};font-weight:bold;")
        else:
            label.setStyleSheet(f"color:{C['cyan']};font-weight:bold;")

    def _pick_photo(self):
        path, _selected_filter = QFileDialog.getOpenFileName(
            self,
            "Выбрать фото",
            "",
            "Images (*.png *.jpg *.jpeg *.bmp *.webp)",
        )
        if not path:
            return
        self._selected_photo = path
        self._photo_result_path = ""
        self.photo_path.setText(path)
        self._set_preview(self.photo_preview, path, "PHOTO PREVIEW")
        self.photo_status_lbl.setText("PHOTO READY")
        self.photo_status_lbl.setStyleSheet(f"color:{C['green']};font-size:10px;")
        self._log(f"Photo selected: {path}", C["cyan"])

    def _set_preview(self, label, path, fallback_text):
        pixmap = QPixmap(path)
        if pixmap.isNull():
            label.setText(fallback_text)
            label.setPixmap(QPixmap())
            return
        label.setText("")
        label.setPixmap(
            pixmap.scaled(
                label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._selected_photo:
            self._set_preview(self.photo_preview, self._selected_photo, "PHOTO PREVIEW")
            preview_path = self._photo_result_path or self._selected_photo
            self._set_preview(self.photo_result_preview, preview_path, "RESULT PREVIEW")

    def _require_photo(self):
        if self._selected_photo:
            return True
        self._log("Сначала выберите фото", C["red"])
        self.photo_status_lbl.setText("NO PHOTO")
        self.photo_status_lbl.setStyleSheet(f"color:{C['red']};font-size:10px;")
        return False

    def _send_photo_to_pc(self):
        if not self._require_photo():
            return
        try:
            upload_path = self.photo_upload_path.text().strip() or "/upload"
            if not upload_path.startswith("/"):
                upload_path = "/" + upload_path
            with open(self._selected_photo, "rb") as photo_file:
                response = requests.post(
                    f"{self._server_url()}{upload_path}",
                    files={"file": (os.path.basename(self._selected_photo), photo_file, "image/jpeg")},
                    data={"meta": self.photo_meta.text().strip()},
                    timeout=10,
                )
            response.raise_for_status()
            self._show_photo_result("PC SERVER RESULT", response)
            self._log("Photo sent to PC server", C["amber"])
        except Exception as exc:
            self._log(f"Photo upload failed: {exc}", C["red"])
            self.photo_status_lbl.setText("UPLOAD FAILED")
            self.photo_status_lbl.setStyleSheet(f"color:{C['red']};font-size:10px;")

    def _send_photo_to_ai(self):
        if not self._require_photo():
            return
        mode = self.photo_mode.currentText()
        if self._ai_backend == "local":
            if not self.local_ai.is_ready:
                self._log("Local AI not loaded. Click LOAD AI.", C["red"])
                return
            try:
                import cv2
            except ImportError:
                self._log("pip install opencv-python", C["red"])
                return
            try:
                image = cv2.imread(self._selected_photo)
                if image is None:
                    raise RuntimeError("Cannot read image")
                detections = self.local_ai.infer_frame(image, mode, self.conf_sl.value() / 100)
                result = {
                    "backend": "local",
                    "model": self.local_ai.model_name,
                    "mode": mode,
                    "detections": detections,
                }
                text = json.dumps(result, ensure_ascii=False, indent=2)
                self.photo_result.setPlainText(f"LOCAL YOLO {mode.upper()} RESULT\n\n{text}")
                self._photo_result_path = self._render_local_ai_preview(
                    image, detections, self._selected_photo
                )
                preview_path = self._photo_result_path or self._selected_photo
                self._set_preview(self.photo_result_preview, preview_path, "RESULT PREVIEW")
                self.photo_status_lbl.setText("DONE")
                self.photo_status_lbl.setStyleSheet(f"color:{C['green']};font-size:10px;")
                self._log(f"Photo analyzed via LOCAL YOLO [{mode}]", C["green"])
            except Exception as exc:
                self._log(f"Local YOLO failed: {exc}", C["red"])
                self._photo_result_path = ""
                self.photo_status_lbl.setText("AI FAILED")
                self.photo_status_lbl.setStyleSheet(f"color:{C['red']};font-size:10px;")
        else:
            try:
                with open(self._selected_photo, "rb") as photo_file:
                    response = requests.post(
                        f"{self._server_url()}/{mode}",
                        files={"file": (os.path.basename(self._selected_photo), photo_file, "image/jpeg")},
                        params={"conf": self.conf_sl.value() / 100},
                        timeout=10,
                    )
                response.raise_for_status()
                self._show_photo_result(f"YOLO {mode.upper()} RESULT", response)
                self._photo_result_path = ""
                self._set_preview(self.photo_result_preview, self._selected_photo, "RESULT PREVIEW")
                self._log(f"Photo analyzed via YOLO [{mode}]", C["green"])
            except Exception as exc:
                self._log(f"YOLO photo request failed: {exc}", C["red"])
                self.photo_status_lbl.setText("AI FAILED")
                self.photo_status_lbl.setStyleSheet(f"color:{C['red']};font-size:10px;")

    def _send_photo_both(self):
        self._send_photo_to_pc()
        self._send_photo_to_ai()

    def _show_photo_result(self, title, response):
        text = ""
        try:
            text = json.dumps(response.json(), ensure_ascii=False, indent=2)
        except ValueError:
            text = response.text
        self.photo_result.setPlainText(f"{title}\n\n{text}")
        self.photo_status_lbl.setText("DONE")
        self.photo_status_lbl.setStyleSheet(f"color:{C['green']};font-size:10px;")

    def _render_local_ai_preview(self, image, detections, src_path):
        try:
            import cv2
        except ImportError:
            return ""

        try:
            canvas = image.copy()
            for detection in detections:
                box = detection.get("box", [0, 0, 0, 0])
                x1, y1, x2, y2 = map(int, box)
                name = detection.get("class_name", "?")
                conf = detection.get("confidence", 0.0)
                tid = detection.get("track_id")
                label = f"{name} {conf:.2f}" + (f" #{tid}" if tid is not None else "")
                cv2.rectangle(canvas, (x1, y1), (x2, y2), (0, 229, 255), 2)
                cv2.rectangle(canvas, (x1, y1 - 18), (x1 + len(label) * 7, y1), (0, 229, 255), -1)
                cv2.putText(
                    canvas,
                    label,
                    (x1 + 2, y1 - 4),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.45,
                    (4, 6, 10),
                    1,
                )

            base = os.path.splitext(os.path.basename(src_path))[0]
            out_path = os.path.join("/tmp", f"{base}_local_ai.jpg")
            cv2.imwrite(out_path, canvas)
            return out_path
        except Exception:
            return ""

    def closeEvent(self, event):
        self._ping_timer.stop()
        self.yolo.stop()
        self.ssh.stop()
        self.ard.stop()
        self.yolo.wait(1000)
        self.ssh.wait(1000)
        self.ard.wait(1000)
        event.accept()


def run():
    app = QApplication(sys.argv)
    app.setApplicationName("Robo Neural Command")
    window = RoboNeural()
    window.show()
    sys.exit(app.exec())
