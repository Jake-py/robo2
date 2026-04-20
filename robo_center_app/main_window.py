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
    QScrollArea,
    QSlider,
    QSplitter,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .theme import C, SS
from .widgets import Led, RadarWidget
from .workers import (
    ArduinoWorker,
    LocalYoloEngine,
    LocalOcrEngine,
    SSHWorker,
    YoloModelManager,
    YoloStream,
    scan_local_models,
)


# ---------------------------------------------------------------------------
# Model slot card widget
# ---------------------------------------------------------------------------

class ModelSlotCard(QFrame):
    """A compact card representing one AI model slot (PRIMARY / SECONDARY / TERTIARY)."""

    SLOT_COLORS = {
        "PRIMARY":   "#00e5ff",   # cyan
        "SECONDARY": "#00ff9d",   # green
        "TERTIARY":  "#9945ff",   # purple
    }

    def __init__(self, slot_name: str, model_list: list, parent=None):
        super().__init__(parent)
        self.slot_name = slot_name
        self._color = self.SLOT_COLORS.get(slot_name, C["cyan"])
        self.setObjectName("ModelSlotCard")
        self.setStyleSheet(f"""
            QFrame#ModelSlotCard {{
                background: {C['panel']};
                border: 1px solid {C['border']};
                border-left: 3px solid {self._color};
                border-radius: 2px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        # Header row: slot name + active radio + LED
        header = QHBoxLayout()
        slot_lbl = QLabel(slot_name)
        slot_lbl.setStyleSheet(
            f"color:{self._color};font-size:9px;font-weight:bold;letter-spacing:3px;"
        )
        header.addWidget(slot_lbl)
        header.addStretch()

        self.active_btn = QPushButton("SET ACTIVE")
        self.active_btn.setFixedHeight(18)
        self.active_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C['raised']}; color: {C['text2']};
                border: 1px solid {C['border2']}; border-radius:1px;
                font-size:8px; letter-spacing:1px; padding:0 6px;
            }}
            QPushButton:hover {{ border-color:{self._color}; color:{self._color}; }}
            QPushButton:checked {{
                background:{self._color}; color:{C['void']};
                border-color:{self._color}; font-weight:bold;
            }}
        """)
        self.active_btn.setCheckable(True)
        header.addWidget(self.active_btn)

        self.led = Led(8)
        header.addWidget(self.led)
        layout.addLayout(header)

        # Model selector
        model_row = QHBoxLayout()
        self.model_cb = QComboBox()
        self.model_cb.setStyleSheet(f"""
            QComboBox {{
                background:{C['deep']}; color:{C['text']};
                border:1px solid {C['border']}; border-radius:2px; padding:3px 6px;
                font-size:10px;
            }}
            QComboBox:focus {{ border-color:{self._color}; }}
            QComboBox QAbstractItemView {{
                background:{C['deep']}; color:{C['text']};
                border:1px solid {C['border2']}; selection-background-color:{C['raised']};
            }}
        """)
        self._populate_models(model_list)
        model_row.addWidget(self.model_cb, 1)
        layout.addLayout(model_row)

        # Device + enable row
        ctrl_row = QHBoxLayout()
        self.device_cb = QComboBox()
        self.device_cb.addItems(["cpu", "cuda:0", "cuda:1", "mps"])
        self.device_cb.setFixedWidth(80)
        self.device_cb.setStyleSheet(f"""
            QComboBox {{
                background:{C['deep']}; color:{C['text2']};
                border:1px solid {C['border']}; border-radius:2px; padding:2px 4px;
                font-size:9px;
            }}
        """)
        ctrl_row.addWidget(self.device_cb)

        self.enable_chk = QCheckBox("ON")
        self.enable_chk.setStyleSheet(f"""
            QCheckBox {{ color:{self._color}; font-size:9px; letter-spacing:2px; spacing:4px; }}
            QCheckBox::indicator {{
                width:11px; height:11px;
                border:1px solid {self._color}; border-radius:1px;
                background:{C['deep']};
            }}
            QCheckBox::indicator:checked {{ background:{self._color}; }}
        """)
        self.enable_chk.setChecked(True)
        ctrl_row.addWidget(self.enable_chk)
        ctrl_row.addStretch()

        layout.addLayout(ctrl_row)

        # Action buttons
        btn_row = QHBoxLayout()
        self.btn_load = QPushButton("LOAD")
        self.btn_load.setFixedHeight(22)
        self.btn_load.setStyleSheet(f"""
            QPushButton {{
                background:{C['raised']}; color:{self._color};
                border:1px solid {self._color}; border-radius:1px;
                font-size:9px; letter-spacing:2px;
            }}
            QPushButton:hover {{ background:{self._color}; color:{C['void']}; }}
            QPushButton:disabled {{ color:{C['text3']}; border-color:{C['border']}; background:{C['deep']}; }}
        """)
        btn_row.addWidget(self.btn_load)

        self.btn_unload = QPushButton("UNLOAD")
        self.btn_unload.setFixedHeight(22)
        self.btn_unload.setEnabled(False)
        self.btn_unload.setStyleSheet(f"""
            QPushButton {{
                background:{C['raised']}; color:{C['text2']};
                border:1px solid {C['border2']}; border-radius:1px;
                font-size:9px; letter-spacing:2px;
            }}
            QPushButton:hover {{ background:{C['red']}; color:white; border-color:{C['red']}; }}
            QPushButton:disabled {{ color:{C['text3']}; border-color:{C['border']}; background:{C['deep']}; }}
        """)
        btn_row.addWidget(self.btn_unload)
        layout.addLayout(btn_row)

        # Status label
        self.status_lbl = QLabel("NOT LOADED")
        self.status_lbl.setStyleSheet(f"color:{C['text3']};font-size:9px;letter-spacing:1px;")
        layout.addWidget(self.status_lbl)

    def _populate_models(self, model_list):
        self.model_cb.clear()
        for name, label, path in model_list:
            self.model_cb.addItem(label, userData={"name": name, "path": path})

    def refresh_models(self, model_list):
        current = self.model_cb.currentData()
        self._populate_models(model_list)
        # Try to restore selection
        for i in range(self.model_cb.count()):
            if self.model_cb.itemData(i) == current:
                self.model_cb.setCurrentIndex(i)
                break

    def selected_model(self) -> str:
        data = self.model_cb.currentData()
        if isinstance(data, dict):
            return data.get("name") or self.model_cb.currentText()
        return data or self.model_cb.currentText()

    def selected_model_ref(self) -> str:
        data = self.model_cb.currentData()
        if isinstance(data, dict):
            return data.get("path") or data.get("name") or self.model_cb.currentText()
        return data or self.model_cb.currentText()

    def selected_device(self) -> str:
        return self.device_cb.currentText()

    def set_loaded(self, model_name: str, device: str):
        self.btn_load.setEnabled(False)
        self.btn_unload.setEnabled(True)
        self.led.set(C["green"])
        self.status_lbl.setText(f"LOADED  {model_name}  [{device}]")
        self.status_lbl.setStyleSheet(f"color:{C['green']};font-size:9px;")

    def set_unloaded(self):
        self.btn_load.setEnabled(True)
        self.btn_unload.setEnabled(False)
        self.led.set(C["text3"])
        self.status_lbl.setText("NOT LOADED")
        self.status_lbl.setStyleSheet(f"color:{C['text3']};font-size:9px;")

    def set_error(self, msg: str):
        self.btn_load.setEnabled(True)
        self.btn_unload.setEnabled(False)
        self.led.set(C["red"], True)
        self.status_lbl.setText(f"ERROR: {msg[:40]}")
        self.status_lbl.setStyleSheet(f"color:{C['red']};font-size:9px;")

    def set_active(self, is_active: bool):
        self.active_btn.setChecked(is_active)
        border_color = self.SLOT_COLORS.get(self.slot_name, C["cyan"])
        bg = C["raised"] if is_active else C["panel"]
        self.setStyleSheet(f"""
            QFrame#ModelSlotCard {{
                background: {bg};
                border: 1px solid {'#243650' if not is_active else border_color};
                border-left: 3px solid {border_color};
                border-radius: 2px;
            }}
        """)


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class RoboNeural(QMainWindow):
    RIGHT_HAND_SERVOS = [
        ("P0", "PIN 0", 0),
        ("P1", "PIN 1", 1),
        ("P2", "PIN 2", 2),
        ("P3", "PIN 3", 3),
        ("P4", "PIN 4", 4),
        ("P5", "PIN 5", 5),
        ("P6", "PIN 6", 6),
        ("P7", "PIN 7", 7),
        ("P8", "PIN 8", 8),
        ("P9", "PIN 9", 9),
        ("P10", "PIN 10", 10),
        ("P11", "PIN 11", 11),
        ("P12", "PIN 12", 12),
        ("P13", "PIN 13", 13),
    ]

    WHEEL_PINS = [
        ("P0", 0), ("P1", 1), ("P2", 2), ("P3", 3), ("P4", 4),
        ("P5", 5), ("P6", 6), ("P7", 7), ("P8", 8), ("P9", 9),
        ("P10", 10), ("P11", 11), ("P12", 12),
    ]

    def __init__(self):
        super().__init__()
        self.setWindowTitle("⬡  ROBO NEURAL COMMAND")
        self.setMinimumSize(1500, 920)
        self.setStyleSheet(SS)

        self.ssh = SSHWorker()
        self.yolo = YoloStream()
        self.ard = ArduinoWorker()

        # Multi-model manager replaces single LocalYoloEngine
        self.model_mgr = YoloModelManager()

        self.local_ai = self.model_mgr.active_engine()

        self.ssh.out.connect(self._ssh_out)
        self.ssh.status.connect(self._ssh_status)
        self.ssh.server_info.connect(self._ssh_server_info)
        self.yolo.frame.connect(self._on_frame)
        self.yolo.fps_sig.connect(self._on_fps)
        self.yolo.err.connect(lambda e: self._log(e, C["red"]))
        self.ard.rx.connect(self._ard_rx)
        self.ard.status.connect(self._ard_status)

        self._fps = 0.0
        self._latency = 0.0
        self._det_count = 0
        self._last_ping_ok = None
        self._connected_server_ip = ""
        self._connected_server_host = ""
        self._selected_photo = ""
        self._photo_result_path = ""
        self._ai_backend = "remote"
        self.ocr_engine = LocalOcrEngine()
        self._ocr_items = []
        self._right_hand_widgets = {}
        self._wheel_widgets = {}

        # Cached model scan results
        self._model_list = scan_local_models()

        self._build_ui()
        self._ai_backend_changed(self.ai_backend_cb.currentText())
        self._refresh_ports()
        self._update_photo_target()

        self._ping_timer = QTimer(self)
        self._ping_timer.timeout.connect(self._ping)
        self._ping_timer.start(4000)
        self._ping()

        self._ai_status_timer = QTimer(self)
        self._ai_status_timer.timeout.connect(self._refresh_ai_status_tab)
        self._ai_status_timer.start(1000)

    # -----------------------------------------------------------------------
    # UI build
    # -----------------------------------------------------------------------

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
        self.srv_lbl.setStyleSheet(f"color:{C['text2']};font-size:9px;letter-spacing:3px;")
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

        # SSH
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

        # Arduino / ESP
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
        usb_lbl.setStyleSheet(f"color:{C['text3']};font-size:9px;letter-spacing:2px;margin-top:4px;")
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
        wifi_lbl.setStyleSheet(f"color:{C['text3']};font-size:9px;letter-spacing:2px;margin-top:4px;")
        ard_layout.addWidget(wifi_lbl)
        self.wifi_en = QCheckBox("ESP WiFi режим")
        ard_layout.addWidget(self.wifi_en)
        row = QHBoxLayout()
        row.addWidget(self._label("IP", 9, fixed=20))
        self.esp_ip = QLineEdit("192.168.1.100")
        row.addWidget(self.esp_ip)
        ard_layout.addLayout(row)

        bt_lbl = QLabel("── BLUETOOTH ──")
        bt_lbl.setStyleSheet(f"color:{C['text3']};font-size:9px;letter-spacing:2px;margin-top:4px;")
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

        # Vision stream
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
        self.cam_src.setPlaceholderText("0 / rtsp:// / http://esp32-ip/stream")
        row.addWidget(self.cam_src)
        vis_layout.addLayout(row)

        row = QHBoxLayout()
        row.addWidget(self._label("CONF", 9, fixed=34))
        self.conf_sl = QSlider(Qt.Orientation.Horizontal)
        self.conf_sl.setRange(10, 90)
        self.conf_sl.setValue(25)
        self.conf_lbl = QLabel("0.25")
        self.conf_lbl.setFixedWidth(34)
        self.conf_sl.valueChanged.connect(lambda v: self.conf_lbl.setText(f"{v / 100:.2f}"))
        row.addWidget(self.conf_sl)
        row.addWidget(self.conf_lbl)
        vis_layout.addLayout(row)

        row = QHBoxLayout()
        self.ocr_live_chk = QCheckBox("OCR")
        self.ocr_live_chk.setChecked(False)
        self.ocr_live_chk.stateChanged.connect(lambda _state: self._sync_local_stream_engine())
        row.addWidget(self.ocr_live_chk)
        row.addWidget(self._label("LANG", 9, fixed=34))
        self.ocr_lang_in = QLineEdit("eng")
        self.ocr_lang_in.setPlaceholderText("eng / rus / eng+rus")
        self.ocr_lang_in.editingFinished.connect(self._sync_local_stream_engine)
        row.addWidget(self.ocr_lang_in)
        row.addStretch()
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

        # AI ENGINE — multi-model panel
        layout.addWidget(self._ai_engine_panel())

        layout.addStretch()
        return widget

    def _ai_engine_panel(self) -> QGroupBox:
        """Build the full AI ENGINE panel with backend selector + 3 model slot cards."""
        ai_box = QGroupBox("AI ENGINE")
        ai_layout = QVBoxLayout(ai_box)
        ai_layout.setSpacing(6)

        # Backend selector row
        backend_row = QHBoxLayout()
        backend_row.addWidget(self._label("BACKEND", 9, fixed=56))
        self.ai_backend_cb = QComboBox()
        self.ai_backend_cb.addItems(["SERVER HTTP", "LOCAL YOLO"])
        self.ai_backend_cb.currentTextChanged.connect(self._ai_backend_changed)
        backend_row.addWidget(self.ai_backend_cb, 1)

        # Scan button
        self.btn_scan_models = QPushButton("⟳ SCAN")
        self.btn_scan_models.setFixedHeight(24)
        self.btn_scan_models.setFixedWidth(64)
        self.btn_scan_models.setStyleSheet(f"""
            QPushButton {{
                background:{C['raised']}; color:{C['cyan']};
                border:1px solid {C['border2']}; border-radius:2px;
                font-size:9px; letter-spacing:1px;
            }}
            QPushButton:hover {{ background:{C['surface']}; border-color:{C['cyan']}; }}
        """)
        self.btn_scan_models.clicked.connect(self._scan_models)
        backend_row.addWidget(self.btn_scan_models)
        ai_layout.addLayout(backend_row)

        # Active slot indicator
        active_row = QHBoxLayout()
        active_row.addWidget(self._label("ACTIVE", 9, fixed=56))
        self.active_slot_lbl = QLabel("PRIMARY")
        self.active_slot_lbl.setStyleSheet(
            f"color:{C['cyan']};font-size:9px;font-weight:bold;letter-spacing:2px;"
        )
        active_row.addWidget(self.active_slot_lbl)
        active_row.addStretch()
        self.ai_led = Led(8)
        active_row.addWidget(self.ai_led)
        self.ai_lbl = QLabel("REMOTE")
        self.ai_lbl.setStyleSheet(f"color:{C['text2']};font-size:9px;")
        active_row.addWidget(self.ai_lbl)
        ai_layout.addLayout(active_row)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color:{C['border']};")
        ai_layout.addWidget(sep)

        # Model slot cards inside a scroll area (they can be tall)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical { width: 4px; background: transparent; }
            QScrollBar::handle:vertical { background: #1a2840; border-radius: 2px; }
        """)
        cards_widget = QWidget()
        cards_widget.setStyleSheet("background: transparent;")
        cards_layout = QVBoxLayout(cards_widget)
        cards_layout.setContentsMargins(0, 0, 0, 0)
        cards_layout.setSpacing(5)

        self._slot_cards: dict[str, ModelSlotCard] = {}
        for slot in ["PRIMARY", "SECONDARY", "TERTIARY"]:
            card = ModelSlotCard(slot, self._model_list)
            card.btn_load.clicked.connect(lambda _=False, s=slot: self._ai_load(s))
            card.btn_unload.clicked.connect(lambda _=False, s=slot: self._ai_unload(s))
            card.active_btn.clicked.connect(lambda _=False, s=slot: self._ai_set_active(s))
            card.enable_chk.stateChanged.connect(
                lambda state, s=slot: self._ai_enable_toggle(s, state)
            )
            self._slot_cards[slot] = card
            cards_layout.addWidget(card)

        cards_layout.addStretch()
        scroll.setWidget(cards_widget)
        scroll.setMinimumHeight(300)
        ai_layout.addWidget(scroll, 1)

        # Mark PRIMARY as default active
        self._slot_cards["PRIMARY"].set_active(True)

        return ai_box

    # -----------------------------------------------------------------------
    # Center panel / tabs
    # -----------------------------------------------------------------------

    def _center_panel(self):
        tabs = QTabWidget()
        tabs.addTab(self._tab_vision(), "VISION")
        tabs.addTab(self._tab_photo(), "PHOTO")
        tabs.addTab(self._tab_ssh(), "TERMINAL")
        tabs.addTab(self._tab_robot(), "ROBOT")
        tabs.addTab(self._tab_right_hand(), "ПРАВАЯ РУКА")
        tabs.addTab(self._tab_wheels(), "Колеса")
        tabs.addTab(self._tab_arduino(), "ARDUINO")
        tabs.addTab(self._tab_ai_status(), "AI STATUS")
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
        self.hud_ocr = self._badge("OCR", "0", C["green_dim"])
        self.hud_mode = self._badge("MODE", "—", C["purple"])
        self.hud_model = self._badge("MODEL", "—", C["cyan"])
        for badge in [self.hud_fps, self.hud_lat, self.hud_obj, self.hud_ocr, self.hud_mode, self.hud_model]:
            hud.addWidget(badge)
        hud.addStretch()
        layout.addLayout(hud)

        self.vid = QLabel("NO SIGNAL")
        self.vid.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.vid.setMinimumHeight(380)
        self.vid.setStyleSheet(f"""
            background:{C['void']};color:{C['text3']};
            border:1px solid {C['border']};
            font-size:20px;letter-spacing:8px;
        """)
        layout.addWidget(self.vid, 1)

        self.det_view = QTextEdit()
        self.det_view.setReadOnly(True)
        self.det_view.setMaximumHeight(110)
        self.det_view.setStyleSheet(f"""
            background:{C['void']};color:{C['green']};
            border:1px solid {C['border']};font-size:11px;
        """)
        layout.addWidget(self.det_view)
        return widget

    def _tab_photo(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        source_box = QGroupBox("SOURCE")
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
        self.photo_meta.setPlaceholderText("Доп. данные: scene=lobby, camera=front")
        meta_row.addWidget(self.photo_meta, 1)
        self.photo_ocr_chk = QCheckBox("OCR")
        self.photo_ocr_chk.setChecked(True)
        meta_row.addWidget(self.photo_ocr_chk)
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
        for label, row_idx, col_idx, cmd in moves:
            button = QPushButton(label)
            button.setStyleSheet(
                button_style if cmd != "STOP" else button_style.replace(C["text"], C["red"])
            )
            button.clicked.connect(
                lambda _checked=False, direction=cmd: self._move(direction)
            )
            grid.addWidget(button, row_idx, col_idx)

        speed_row = QHBoxLayout()
        speed_row.addWidget(self._label("SPEED", 9, fixed=46))
        self.spd_sl = QSlider(Qt.Orientation.Horizontal)
        self.spd_sl.setRange(0, 255)
        self.spd_sl.setValue(130)
        self.spd_lbl = QLabel("130")
        self.spd_lbl.setFixedWidth(32)
        self.spd_sl.valueChanged.connect(lambda v: self.spd_lbl.setText(str(v)))
        speed_row.addWidget(self.spd_sl)
        speed_row.addWidget(self.spd_lbl)
        grid.addLayout(speed_row, 3, 0, 1, 3)
        layout.addWidget(move_box)

        layout.addStretch()
        return widget

    def _tab_right_hand(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        head = QGroupBox("ПИНЫ 0..13 · РУЧНОЕ УПРАВЛЕНИЕ")
        head_layout = QHBoxLayout(head)
        title = QLabel("Диапазон сервоприводов: 0° … 180°")
        title.setStyleSheet(f"color:{C['cyan']};font-weight:bold;font-size:12px;")
        head_layout.addWidget(title)
        head_layout.addStretch()
        btn_home = self._btn("ВСЕ В 0°", C["amber"])
        btn_home.clicked.connect(self._home_all_right_hand)
        head_layout.addWidget(btn_home)
        btn_status = self._btn("ОБНОВИТЬ СТАТУС")
        btn_status.clicked.connect(lambda: self._ard_send("STATUS"))
        head_layout.addWidget(btn_status)
        layout.addWidget(head)

    def _tab_wheels(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        head = QGroupBox("ПИНЫ 0..12 · МОТОРЫ КОЛЁС")
        head_layout = QHBoxLayout(head)
        title = QLabel("Скорость PWM: 0 … 255")
        title.setStyleSheet(f"color:{C['cyan']};font-weight:bold;font-size:12px;")
        head_layout.addWidget(title)
        head_layout.addStretch()
        btn_all_off = self._btn("ВСЕ ОФФ", C["amber"])
        btn_all_off.clicked.connect(self._wheels_all_off)
        head_layout.addWidget(btn_all_off)
        btn_status = self._btn("ОБНОВИТЬ СТАТУС")
        btn_status.clicked.connect(lambda: self._ard_send("STATUS"))
        head_layout.addWidget(btn_status)
        layout.addWidget(head)

        # Wheels checkboxes grid
        wheels_box = QGroupBox("ПИНЫ ДЛЯ ВЫБОРА")
        wheels_grid = QGridLayout(wheels_box)
        wheels_grid.setSpacing(8)
        for row, (pid, pin_num) in enumerate(self.WHEEL_PINS):
            col = row % 6  # 6 columns
            rrow = row // 6

            chk = QCheckBox(pid)
            chk.setStyleSheet(f"""
                QCheckBox {{ color:{C['cyan']}; font-size:11px; letter-spacing:2px; spacing:6px; }}
                QCheckBox::indicator {{ width:16px; height:16px; border:1px solid {C['border']}; border-radius:3px; background:{C['deep']}; }}
                QCheckBox::indicator:checked {{ background:{C['green']}; border-color:{C['green']}; }}
            """)
            chk.stateChanged.connect(lambda state, p=pid: self._wheel_pin_toggled(p, state > 0))
            wheels_grid.addWidget(chk, rrow, col)
            self._wheel_widgets[pid] = chk

        layout.addWidget(wheels_box)

        # Speed control
        speed_group = QGroupBox("СКОРОСТЬ")
        speed_layout = QHBoxLayout(speed_group)
        speed_layout.addWidget(self._label("SPEED", 9, fixed=46))
        self.wheel_speed_sl = QSlider(Qt.Orientation.Horizontal)
        self.wheel_speed_sl.setRange(0, 255)
        self.wheel_speed_sl.setValue(128)
        self.wheel_speed_sl.setStyleSheet(
            f"QSlider::groove:horizontal{{height:12px;background:{C['panel']};border:1px solid {C['border']};border-radius:4px;}}"
            f"QSlider::handle:horizontal{{width:20px;background:{C['amber']};margin:-6px 0;border-radius:4px;}}"
        )
        self.wheel_speed_lbl = QLabel("128")
        self.wheel_speed_lbl.setStyleSheet(f"color:{C['amber']};font-weight:bold;font-size:12px;")
        self.wheel_speed_lbl.setFixedWidth(40)
        self.wheel_speed_sl.valueChanged.connect(
            lambda v: self.wheel_speed_lbl.setText(str(v))
        )
        speed_layout.addWidget(self.wheel_speed_sl)
        speed_layout.addWidget(self.wheel_speed_lbl)
        layout.addWidget(speed_group)

        # Control buttons
        btn_group = QGroupBox("УПРАВЛЕНИЕ")
        btn_layout = QHBoxLayout(btn_group)
        btn_layout.setSpacing(8)

        self.btn_wheel_fwd = self._btn("ВПЕРЁД", C["green"])
        self.btn_wheel_fwd.clicked.connect(self._wheels_forward)
        btn_layout.addWidget(self.btn_wheel_fwd)

        self.btn_wheel_bkwd = self._btn("НАЗАД", C["red"])
        self.btn_wheel_bkwd.clicked.connect(self._wheels_backward)
        btn_layout.addWidget(self.btn_wheel_bkwd)

        self.btn_wheel_stop = self._btn("СТОП", C["amber"])
        self.btn_wheel_stop.clicked.connect(self._wheels_stop)
        btn_layout.addWidget(self.btn_wheel_stop)

        layout.addWidget(btn_group)

        # Individual pin control
        indiv_group = QGroupBox("ИНДИВИДУАЛЬНОЕ УПРАВЛЕНИЕ ПИНАМИ")
        indiv_layout = QGridLayout(indiv_group)
        indiv_layout.setSpacing(4)
        for row, (pid, pin_num) in enumerate(self.WHEEL_PINS):
            col = 0
            lbl = QLabel(f"{pid} (PIN {pin_num})")
            lbl.setStyleSheet(f"color:{C['cyan']};font-size:10px;")
            indiv_layout.addWidget(lbl, row, col)

            fwd_btn = self._btn("FWD", C["green"], small=True)
            fwd_btn.clicked.connect(lambda _, p=pid: self._wheel_individual_fwd(p))
            indiv_layout.addWidget(fwd_btn, row, col+1)

            bkwd_btn = self._btn("BKWD", C["red"], small=True)
            bkwd_btn.clicked.connect(lambda _, p=pid: self._wheel_individual_bkwd(p))
            indiv_layout.addWidget(bkwd_btn, row, col+2)

            stop_btn = self._btn("STOP", C["amber"], small=True)
            stop_btn.clicked.connect(lambda _, p=pid: self._wheel_individual_stop(p))
            indiv_layout.addWidget(stop_btn, row, col+3)

        layout.addWidget(indiv_group)

        info = QLabel("Выберите пины → установите скорость → нажмите ВПЕРЁД/НАЗАД/СТОП\nИли используйте индивидуальное управление каждым пином")
        info.setStyleSheet(f"color:{C['text2']};font-size:10px;")
        layout.addWidget(info)
        layout.addStretch()
        return widget

        hand_box = QGroupBox("СЕРВОПРИВОДЫ")
        hand_grid = QGridLayout(hand_box)
        hand_grid.setHorizontalSpacing(10)
        hand_grid.setVerticalSpacing(8)
        for row, (sid, name, pin) in enumerate(self.RIGHT_HAND_SERVOS):
            hand_grid.addWidget(self._label(f"{name} ({sid})", 10, fixed=118), row, 0)

            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(0, 180)
            slider.setValue(0)
            slider.setStyleSheet(
                f"QSlider::groove:horizontal{{height:8px;background:{C['panel']};border:1px solid {C['border']};}}"
                f"QSlider::handle:horizontal{{width:16px;background:{C['cyan']};margin:-4px 0;border-radius:2px;}}"
            )
            hand_grid.addWidget(slider, row, 1)

            angle_lbl = QLabel("0°")
            angle_lbl.setStyleSheet(f"color:{C['green']};font-weight:bold;")
            angle_lbl.setFixedWidth(44)
            hand_grid.addWidget(angle_lbl, row, 2)

            pin_lbl = QLabel(f"PIN {pin}")
            pin_lbl.setStyleSheet(f"color:{C['text3']};font-size:9px;")
            pin_lbl.setFixedWidth(50)
            hand_grid.addWidget(pin_lbl, row, 3)

            for col, fixed_angle in enumerate([0, 90, 180], start=4):
                btn = QPushButton(str(fixed_angle))
                btn.setFixedWidth(42)
                btn.setStyleSheet("font-size:9px;")
                btn.clicked.connect(
                    lambda _=False, s=sid, a=fixed_angle: self._set_right_hand_angle(s, a)
                )
                hand_grid.addWidget(btn, row, col)

            sweep_btn = QPushButton("SWEEP")
            sweep_btn.setFixedWidth(64)
            sweep_btn.setStyleSheet("font-size:9px;letter-spacing:1px;")
            sweep_btn.clicked.connect(lambda _=False, s=sid: self._run_servo_sweep(s))
            hand_grid.addWidget(sweep_btn, row, 7)

            slider.valueChanged.connect(
                lambda angle, s=sid, lbl=angle_lbl: (
                    lbl.setText(f"{angle}°"),
                    self._set_right_hand_angle(s, angle, from_slider=True),
                )
            )

            self._right_hand_widgets[sid] = {
                "slider": slider,
                "label": angle_lbl,
            }

        layout.addWidget(hand_box)

        info = QLabel("Профили: P0..P13 соответствуют пинам 0..13")
        info.setStyleSheet(f"color:{C['text2']};font-size:10px;")
        layout.addWidget(info)
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
        self.ard_in.setPlaceholderText("Команда Arduino (например: SERVO:S1:SET:90)")
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
            ("ROBOT", "ROBOT"), ("IR", "IR"), ("ULTRA", "ULTRA"), ("BUMPER", "BUMPER"),
            ("IMU", "IMU"), ("TEMP", "TEMP"), ("BATTERY", "BATTERY"), ("ESP_RSSI", "ESP_RSSI"),
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
        for cmd in ["STATUS", "MOTOR:STOP", "SERVO:ALL:HOME"]:
            qb = QPushButton(cmd)
            qb.setFixedHeight(26)
            qb.setStyleSheet("font-size:9px;letter-spacing:1px;")
            qb.clicked.connect(lambda _=False, v=cmd: self._ard_quick(v))
            quick_layout.addWidget(qb)
        layout.addWidget(quick_box)
        return widget

    def _tab_ai_status(self):
        """Dedicated AI STATUS tab — live overview of all model slots."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        title = QLabel("MODEL SLOT STATUS")
        title.setStyleSheet(
            f"color:{C['cyan']};font-size:11px;font-weight:bold;letter-spacing:4px;"
        )
        layout.addWidget(title)

        self._status_grid = QGridLayout()
        self._status_grid.setSpacing(4)
        headers = ["SLOT", "MODEL", "DEVICE", "STATE", "ENABLED", "ACTIVE"]
        for col, h in enumerate(headers):
            lbl = QLabel(h)
            lbl.setStyleSheet(
                f"color:{C['text3']};font-size:9px;letter-spacing:2px;border-bottom:1px solid {C['border']};"
            )
            self._status_grid.addWidget(lbl, 0, col)

        self._status_rows: dict[str, list] = {}
        for row_idx, slot in enumerate(["PRIMARY", "SECONDARY", "TERTIARY"], start=1):
            color = ModelSlotCard.SLOT_COLORS.get(slot, C["cyan"])
            row_labels = []
            vals = [slot, "—", "—", "NOT LOADED", "YES", "—"]
            for col, val in enumerate(vals):
                lbl = QLabel(val)
                lbl.setStyleSheet(
                    f"color:{color if col == 0 else C['text']};font-size:10px;padding:2px 4px;"
                )
                self._status_grid.addWidget(lbl, row_idx, col)
                row_labels.append(lbl)
            self._status_rows[slot] = row_labels

        layout.addLayout(self._status_grid)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color:{C['border']};margin-top:8px;")
        layout.addWidget(sep)

        # Refresh button
        btn_refresh = self._btn("⟳ REFRESH STATUS", C["blue"])
        btn_refresh.setFixedWidth(180)
        btn_refresh.clicked.connect(lambda: self._refresh_ai_status_tab(log_event=True))
        layout.addWidget(btn_refresh)

        # Log
        self._ai_status_log = QTextEdit()
        self._ai_status_log.setReadOnly(True)
        self._ai_status_log.setStyleSheet(
            f"background:{C['void']};color:{C['text2']};border:1px solid {C['border']};font-size:10px;"
        )
        layout.addWidget(self._ai_status_log, 1)

        layout.addStretch()

        # Initial refresh
        QTimer.singleShot(200, self._refresh_ai_status_tab)
        return widget

    def _refresh_ai_status_tab(self, log_event: bool = False):
        summary = self.model_mgr.status_summary()
        for slot, info in summary.items():
            row = self._status_rows.get(slot)
            if not row:
                continue
            row[1].setText(info["model"] or "—")
            row[2].setText(info["device"])
            state = "LOADED" if info["loaded"] else "NOT LOADED"
            color = C["green"] if info["loaded"] else C["text3"]
            row[3].setText(state)
            row[3].setStyleSheet(f"color:{color};font-size:10px;padding:2px 4px;")
            row[4].setText("ON" if info["enabled"] else "OFF")
            row[4].setStyleSheet(
                f"color:{C['green'] if info['enabled'] else C['red']};font-size:10px;padding:2px 4px;"
            )
            row[5].setText("◉ ACTIVE" if info["active"] else "—")
            row[5].setStyleSheet(
                f"color:{C['cyan'] if info['active'] else C['text3']};font-size:10px;padding:2px 4px;"
            )

        if log_event:
            ts = time.strftime("%H:%M:%S")
            self._ai_status_log.append(
                f'<span style="color:{C["text3"]}">[{ts}]</span> '
                f'<span style="color:{C["text2"]}">Status refreshed</span>'
            )

    # -----------------------------------------------------------------------
    # Right panel
    # -----------------------------------------------------------------------

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
        for i, (name, key) in enumerate([
            ("FPS", "fps"), ("LATENCY", "latency"), ("OBJECTS", "objects"),
            ("TRACKS", "tracks"), ("OCR TEXT", "ocr_text"), ("CONTROL", "control_mode"), ("ROBOT", "robot_cmd"),
            ("ACTIVE MODEL", "active_model"),
        ]):
            stats_grid.addWidget(self._label(name, 9, fixed=88), i, 0)
            label = QLabel("—")
            label.setStyleSheet(f"color:{C['cyan']};font-weight:bold;")
            label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            stats_grid.addWidget(label, i, 1)
            self._stats[key] = label
        self._stats["control_mode"].setText("MANUAL")
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
        bar.setStyleSheet(f"QFrame{{background:{C['deep']};border-top:1px solid {C['border']};}}")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(14, 0, 14, 0)
        self.status_lbl = QLabel("СИСТЕМА ИНИЦИАЛИЗИРОВАНА")
        self.status_lbl.setStyleSheet(f"color:{C['text2']};font-size:9px;letter-spacing:2px;")
        layout.addWidget(self.status_lbl)
        layout.addStretch()
        version = QLabel("ROBO NEURAL v2.1  ·  MULTI-YOLO  ·  CUDA 13.0  ·  RTX 5070 Ti")
        version.setStyleSheet(f"color:{C['text3']};font-size:9px;")
        layout.addWidget(version)
        return bar

    # -----------------------------------------------------------------------
    # Widget helpers
    # -----------------------------------------------------------------------

    def _btn(self, text, color=None, small=False):
        button = QPushButton(text)
        font_size = "8px" if small else "10px"
        padding = "3px 8px" if small else "5px 12px"
        if color:
            button.setStyleSheet(f"""
                QPushButton{{background:{color};color:white;border:none;border-radius:2px;
                padding:{padding};font-size:{font_size};letter-spacing:1px;font-weight:bold;}}
                QPushButton:hover{{opacity:0.9;}}
                QPushButton:disabled{{background:{C['border']};color:{C['text3']};}}
            """)
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

    # -----------------------------------------------------------------------
    # AI Engine — multi-model logic
    # -----------------------------------------------------------------------

    def _scan_models(self):
        self._model_list = scan_local_models()
        for card in self._slot_cards.values():
            card.refresh_models(self._model_list)
        count = sum(1 for n, l, p in self._model_list if l.startswith("[LOCAL]"))
        self._log(f"Model scan: {count} local .pt files found", C["cyan"])

    def _ai_load(self, slot: str):
        card = self._slot_cards[slot]
        model_name = card.selected_model()
        model_ref = card.selected_model_ref()
        device = card.selected_device()
        self._log(f"Loading {model_name} on {slot} [{device}]...", C["amber"])
        try:
            self.model_mgr.load(slot, model_ref, device)
            card.set_loaded(model_name, device)
            self._log(f"{slot}: {model_name} loaded [{device}]", C["green"])
            self._update_active_model_display()
            self._refresh_ai_status_tab()
        except Exception as exc:
            card.set_error(str(exc))
            self._log(f"{slot} load failed: {exc}", C["red"])
            self._refresh_ai_status_tab()

    def _ai_unload(self, slot: str):
        self.model_mgr.unload(slot)
        self._slot_cards[slot].set_unloaded()
        self._log(f"{slot}: model unloaded", C["amber"])
        self._update_active_model_display()
        self._sync_local_stream_engine()
        self._refresh_ai_status_tab()

    def _ai_set_active(self, slot: str):
        self.model_mgr.set_active(slot)
        self.local_ai = self.model_mgr.active_engine()
        # Update all card visual states
        for s, card in self._slot_cards.items():
            card.set_active(s == slot)
        self.active_slot_lbl.setText(slot)
        self._update_active_model_display()
        self._sync_local_stream_engine()
        self._refresh_ai_status_tab()
        self._log(f"Active AI slot: {slot}", C["cyan"])

    def _ai_enable_toggle(self, slot: str, state: int):
        if state > 0:
            self.model_mgr.enable(slot)
            self._log(f"{slot}: AI enabled", C["green"])
        else:
            self.model_mgr.disable(slot)
            self._log(f"{slot}: AI disabled", C["amber"])
        self._update_active_model_display()
        self._sync_local_stream_engine()
        self._refresh_ai_status_tab()

    def _update_active_model_display(self):
        eng = self.model_mgr.active_engine()
        model_short = (eng.model_name.replace(".pt", "") if eng.model_name else "—")
        self._badge_set("MODEL", model_short)
        if hasattr(self, "_stats"):
            self._stats["active_model"].setText(model_short)
        if eng.is_ready:
            self.ai_led.set(C["green"])
            self.ai_lbl.setText("LOCAL READY")
            self.ai_lbl.setStyleSheet(f"color:{C['green']};font-size:9px;")
        elif eng.model is not None and not eng.enabled:
            self.ai_led.set(C["amber"])
            self.ai_lbl.setText("DISABLED")
            self.ai_lbl.setStyleSheet(f"color:{C['amber']};font-size:9px;")
        else:
            if self._ai_backend == "local":
                self.ai_led.set(C["amber"], True)
                self.ai_lbl.setText("NOT LOADED")
                self.ai_lbl.setStyleSheet(f"color:{C['amber']};font-size:9px;")

    def _ai_backend_changed(self, text):
        is_local = "LOCAL" in text
        self._ai_backend = "local" if is_local else "remote"

        # Cards only relevant for local mode
        for card in self._slot_cards.values():
            card.setEnabled(is_local)

        if is_local:
            self._update_active_model_display()
            self._sync_local_stream_engine()
        else:
            self.ai_led.set(C["cyan_dim"])
            self.ai_lbl.setText("REMOTE")
            self.ai_lbl.setStyleSheet(f"color:{C['text2']};font-size:9px;")

        self._refresh_ai_status_tab()
        self._log(f"AI backend: {'LOCAL YOLO' if is_local else 'SERVER HTTP'}", C["cyan"])

    def _sync_local_stream_engine(self):
        self.yolo.set_backend(
            self._ai_backend,
            self.model_mgr.active_engine(),
            self.ocr_engine,
            self.ocr_live_chk.isChecked() if hasattr(self, "ocr_live_chk") else False,
            self.ocr_lang_in.text().strip() if hasattr(self, "ocr_lang_in") else "eng",
        )

    # -----------------------------------------------------------------------
    # Misc handlers (unchanged logic from original)
    # -----------------------------------------------------------------------

    def _refresh_ports(self):
        self.ard_port.clear()
        ports = [p.device for p in serial.tools.list_ports.comports()]
        self.ard_port.addItems(ports if ports else ["(нет портов)"])

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
        if self._ai_backend == "local" and not self.model_mgr.active_engine().is_ready:
            self._log("Active AI not loaded or disabled", C["red"])
            return
        self.yolo.set_backend(self._ai_backend, self.model_mgr.active_engine())
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
        self._ocr_items = []
        self._badge_set("OCR", "0")
        self._log("Vision stopped", C["amber"])

    def _on_frame(self, image: QImage, detections: list, ocr_items: list):
        pixmap = QPixmap.fromImage(image).scaled(
            self.vid.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.vid.setPixmap(pixmap)
        self._det_count = len(detections)
        self._ocr_items = ocr_items or []
        self._badge_set("OBJ", str(self._det_count))
        self._badge_set("OCR", str(len(self._ocr_items)))
        self._stats["objects"].setText(str(self._det_count))
        if hasattr(self, "_stats"):
            self._stats["ocr_text"].setText(str(len(self._ocr_items)))
        track_count = len([d for d in detections if d.get("track_id") is not None])
        self._stats["tracks"].setText(str(track_count))
        self.radar.update_objects(detections)

        lines = []
        if detections:
            for det in detections:
                tid = det.get("track_id")
                lines.append(
                    f"  [{det.get('class_name', '?')}]"
                    + (f" #{tid}" if tid is not None else "")
                    + f"  conf={det.get('confidence', 0):.2f}"
                )
        if self._ocr_items:
            lines.append("")
            lines.append("OCR:")
            for item in self._ocr_items[:8]:
                lines.append(f"  \"{item.get('text', '')}\"  conf={item.get('confidence', 0):.0f}")
        if lines:
            self.det_view.setPlainText("\n".join(lines))
        else:
            self.det_view.clear()

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
            self._log(f"BLE mode: {self.bt_mac.text()}", C["purple"])
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
        if ok:
            QTimer.singleShot(500, self._home_all_right_hand)
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

    def _set_right_hand_angle(self, servo_id, angle, from_slider=False):
        angle = max(0, min(180, int(angle)))
        row = self._right_hand_widgets.get(servo_id)
        if row:
            slider = row["slider"]
            if slider.value() != angle:
                slider.blockSignals(True)
                slider.setValue(angle)
                slider.blockSignals(False)
            row["label"].setText(f"{angle}°")
        self._ard_send(f"SERVO:{servo_id}:SET:{angle}")
        if not from_slider:
            self._log(f"{servo_id} -> {angle}°", C["cyan"])

    def _home_all_right_hand(self):
        self._ard_send("SERVO:ALL:HOME")
        for row in self._right_hand_widgets.values():
            row["slider"].blockSignals(True)
            row["slider"].setValue(0)
            row["slider"].blockSignals(False)
            row["label"].setText("0°")
        self._log("Правая рука: все сервоприводы в 0°", C["green"])

    def _run_servo_sweep(self, servo_id):
        for delay_ms, angle in [(0, 0), (650, 180), (1300, 0)]:
            QTimer.singleShot(
                delay_ms, lambda s=servo_id, a=angle: self._set_right_hand_angle(s, a)
            )
        self._log(f"{servo_id}: тест 0°→180°→0°", C["amber"])

    def _wheel_pin_toggled(self, pid, checked):
        """Track selected wheel pins."""
        if checked:
            self._log(f"Колёса: {pid} включён")
        else:
            self._log(f"Колёса: {pid} выключен")

    def _get_selected_wheel_pins(self):
        """Get list of checked pin IDs."""
        return [pid for pid, chk in self._wheel_widgets.items() if chk.isChecked()]

    def _wheels_forward(self):
        pins = self._get_selected_wheel_pins()
        speed = self.wheel_speed_sl.value()
        if not pins:
            self._log("Выберите хотя бы один пин колеса!", C["red"])
            return
        for pid in pins:
            self._ard_send(f"MOTOR:{pid}:fwd:{speed}")
        self._log(f"Колёса ВПЕРЁД: {', '.join(pins)} speed={speed}", C["green"])

    def _wheels_backward(self):
        pins = self._get_selected_wheel_pins()
        speed = self.wheel_speed_sl.value()
        if not pins:
            self._log("Выберите хотя бы один пин колеса!", C["red"])
            return
        for pid in pins:
            self._ard_send(f"MOTOR:{pid}:bkwd:{speed}")
        self._log(f"Колёса НАЗАД: {', '.join(pins)} speed={speed}", C["red"])

    def _wheels_stop(self):
        pins = self._get_selected_wheel_pins()
        if not pins:
            self._log("Выберите хотя бы один пин колеса!", C["red"])
            return
        for pid in pins:
            self._ard_send(f"MOTOR:{pid}:stop:0")
        self._log(f"Колёса СТОП: {', '.join(pins)}", C["amber"])

    def _wheels_all_off(self):
        for pid in [p[0] for p in self.WHEEL_PINS]:
            self._ard_send(f"MOTOR:{pid}:stop:0")
        self._log("Все колёса ОФФ (0-12)", C["amber"])

    def _wheel_individual_fwd(self, pid):
        speed = self.wheel_speed_sl.value()
        self._ard_send(f"MOTOR:{pid}:fwd:{speed}")
        self._log(f"Колесо {pid} ВПЕРЁД speed={speed}", C["green"])

    def _wheel_individual_bkwd(self, pid):
        speed = self.wheel_speed_sl.value()
        self._ard_send(f"MOTOR:{pid}:bkwd:{speed}")
        self._log(f"Колесо {pid} НАЗАД speed={speed}", C["red"])

    def _wheel_individual_stop(self, pid):
        self._ard_send(f"MOTOR:{pid}:stop:0")
        self._log(f"Колесо {pid} СТОП", C["amber"])

    def _update_photo_target(self):
        target = self._connected_server_ip or self.ip_in.text().strip() or "manual ip"
        if self._connected_server_host:
            target = f"{target} ({self._connected_server_host})"
        self.photo_target_lbl.setText(target)

    def _pick_photo(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Выбрать фото", "", "Images (*.png *.jpg *.jpeg *.bmp *.webp)"
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
            with open(self._selected_photo, "rb") as f:
                response = requests.post(
                    f"{self._server_url()}{upload_path}",
                    files={"file": (os.path.basename(self._selected_photo), f, "image/jpeg")},
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
            eng = self.model_mgr.active_engine()
            if not eng.is_ready:
                self._log("Active AI not loaded. Load a model first.", C["red"])
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
                detections = eng.infer_frame(image, mode, self.conf_sl.value() / 100)
                ocr_items = []
                if self.photo_ocr_chk.isChecked():
                    ocr_items = self.ocr_engine.infer_frame(
                        image,
                        lang=self.ocr_lang_in.text().strip() or "eng",
                    )
                result = {
                    "backend": "local",
                    "model": eng.model_name,
                    "slot": self.model_mgr.active_slot(),
                    "mode": mode,
                    "detections": detections,
                    "ocr": ocr_items,
                }
                text = json.dumps(result, ensure_ascii=False, indent=2)
                self.photo_result.setPlainText(f"LOCAL YOLO {mode.upper()} RESULT\n\n{text}")
                self._photo_result_path = self._render_local_ai_preview(
                    image, detections, self._selected_photo, ocr_items
                )
                preview_path = self._photo_result_path or self._selected_photo
                self._set_preview(self.photo_result_preview, preview_path, "RESULT PREVIEW")
                self.photo_status_lbl.setText("DONE")
                self.photo_status_lbl.setStyleSheet(f"color:{C['green']};font-size:10px;")
                self._log(f"Photo analyzed via {eng.model_name} [{mode}]", C["green"])
            except Exception as exc:
                self._log(f"Local YOLO failed: {exc}", C["red"])
                self._photo_result_path = ""
                self.photo_status_lbl.setText("AI FAILED")
                self.photo_status_lbl.setStyleSheet(f"color:{C['red']};font-size:10px;")
        else:
            try:
                with open(self._selected_photo, "rb") as f:
                    response = requests.post(
                        f"{self._server_url()}/{mode}",
                        files={"file": (os.path.basename(self._selected_photo), f, "image/jpeg")},
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

    def _render_local_ai_preview(self, image, detections, src_path, ocr_items=None):
        try:
            import cv2
        except ImportError:
            return ""
        try:
            canvas = image.copy()
            for det in detections:
                box = det.get("box", [0, 0, 0, 0])
                x1, y1, x2, y2 = map(int, box)
                name = det.get("class_name", "?")
                conf = det.get("confidence", 0.0)
                tid = det.get("track_id")
                label = f"{name} {conf:.2f}" + (f" #{tid}" if tid is not None else "")
                cv2.rectangle(canvas, (x1, y1), (x2, y2), (0, 229, 255), 2)
                cv2.rectangle(canvas, (x1, y1 - 18), (x1 + len(label) * 7, y1), (0, 229, 255), -1)
                cv2.putText(canvas, label, (x1 + 2, y1 - 4),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.45, (4, 6, 10), 1)
            for item in ocr_items or []:
                x1, y1, x2, y2 = map(int, item.get("box", [0, 0, 0, 0]))
                label = f"OCR {item.get('text', '')}"[:30]
                cv2.rectangle(canvas, (x1, y1), (x2, y2), (0, 255, 157), 1)
                top = max(0, y1 - 18)
                cv2.rectangle(canvas, (x1, top), (x1 + min(len(label) * 7, 220), y1), (0, 255, 157), -1)
                cv2.putText(canvas, label, (x1 + 2, max(12, y1 - 4)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.4, (4, 6, 10), 1)
            base = os.path.splitext(os.path.basename(src_path))[0]
            out_path = os.path.join("/tmp", f"{base}_local_ai.jpg")
            cv2.imwrite(out_path, canvas)
            return out_path
        except Exception:
            return ""

    def _parse_sensor_line(self, data):
        if not hasattr(self, "_sensor_labels"):
            return
        raw = data.strip()
        prefixes = ["SENSOR:", "ESP32:", "ESP:"]
        for prefix in prefixes:
            if raw.startswith(prefix):
                rest = raw[len(prefix):].strip()
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
