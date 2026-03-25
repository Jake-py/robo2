"""Background workers for SSH, video and serial device handling."""

import queue
import time

import paramiko
import requests
import serial
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QImage


class SSHWorker(QThread):
    out = pyqtSignal(str)
    status = pyqtSignal(bool, str)
    server_info = pyqtSignal(str, str, str)

    def __init__(self):
        super().__init__()
        self._q = queue.Queue()
        self._host = ""
        self._user = ""
        self._pwd = ""
        self._port = 22
        self._running = False
        self.client = None

    def connect_to_host(self, host, user, pwd, port=22):
        if self.isRunning():
            self.status.emit(False, "SSH already connected or connecting")
            return
        self._host = host
        self._user = user
        self._pwd = pwd
        self._port = port
        self.start()

    def send(self, cmd):
        self._q.put(cmd)

    def stop(self):
        self._running = False
        if self.client:
            self.client.close()

    def run(self):
        try:
            self.client = paramiko.SSHClient()
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.client.connect(
                self._host,
                port=self._port,
                username=self._user,
                password=self._pwd,
                timeout=10,
            )
            channel = self.client.invoke_shell()
            channel.settimeout(0.1)
            self.status.emit(True, f"SSH connected -> {self._user}@{self._host}")
            self._emit_server_info()
            self._running = True
            while self._running:
                try:
                    if channel.recv_ready():
                        self.out.emit(channel.recv(4096).decode("utf-8", "replace"))
                except Exception:
                    pass
                try:
                    cmd = self._q.get_nowait()
                    channel.send(cmd + "\n")
                except queue.Empty:
                    pass
                time.sleep(0.04)
        except Exception as exc:
            self.status.emit(False, f"SSH error: {exc}")
        finally:
            self._running = False
            if self.client:
                self.client.close()
                self.client = None

    def _emit_server_info(self):
        if not self.client:
            return
        hostname = self._host
        primary_ip = self._host
        all_ips = self._host
        try:
            stdin, stdout, _stderr = self.client.exec_command("hostname; hostname -I", timeout=5)
            lines = stdout.read().decode("utf-8", "replace").splitlines()
            if lines:
                hostname = lines[0].strip() or hostname
            if len(lines) > 1:
                ip_list = [ip for ip in lines[1].split() if ip and "." in ip]
                if ip_list:
                    primary_ip = ip_list[0]
                    all_ips = ", ".join(ip_list)
        except Exception:
            pass
        self.server_info.emit(hostname, primary_ip, all_ips)


class YoloStream(QThread):
    frame = pyqtSignal(QImage, list)
    fps_sig = pyqtSignal(float, float)
    err = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._server = ""
        self._src = 0
        self._mode = "detect"
        self._conf = 0.25
        self._running = False
        self._request_error_emitted = False

    def start_stream(self, server, src, mode, conf=0.25):
        if self.isRunning():
            self.err.emit("Vision stream is already running")
            return
        self._server = server.rstrip("/")
        self._src = src
        self._mode = mode
        self._conf = conf
        self._running = True
        self._request_error_emitted = False
        self.start()

    def stop(self):
        self._running = False

    def run(self):
        try:
            import cv2
        except ImportError:
            self.err.emit("pip install opencv-python")
            return

        src = int(self._src) if str(self._src).isdigit() else self._src
        cap = cv2.VideoCapture(src)
        if not cap.isOpened():
            self.err.emit(f"Cannot open source: {src}")
            return

        fps_cnt = 0
        fps_t = time.time()
        latency = 0.0

        while self._running:
            ok, frame = cap.read()
            if not ok:
                self.err.emit("Video source stopped delivering frames")
                break

            _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
            detections = []
            t0 = time.time()
            try:
                response = requests.post(
                    f"{self._server}/{self._mode}",
                    files={"file": ("f.jpg", buf.tobytes(), "image/jpeg")},
                    params={"conf": self._conf},
                    timeout=2,
                )
                response.raise_for_status()
                data = response.json()
                detections = (
                    data.get("detections")
                    or data.get("tracked")
                    or data.get("segments")
                    or []
                )
                latency = (time.time() - t0) * 1000
                self._request_error_emitted = False

                for detection in detections:
                    box = detection.get("box", [0, 0, 0, 0])
                    x1, y1, x2, y2 = map(int, box)
                    name = detection.get("class_name", "?")
                    conf = detection.get("confidence", 0.0)
                    tid = detection.get("track_id")
                    label = f"{name} {conf:.2f}" + (f" #{tid}" if tid is not None else "")
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 229, 255), 2)
                    cv2.rectangle(frame, (x1, y1 - 18), (x1 + len(label) * 7, y1), (0, 229, 255), -1)
                    cv2.putText(
                        frame,
                        label,
                        (x1 + 2, y1 - 4),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.45,
                        (4, 6, 10),
                        1,
                    )
            except Exception as exc:
                latency = 0.0
                if not self._request_error_emitted:
                    self.err.emit(f"Vision request error: {exc}")
                    self._request_error_emitted = True

            rgb = frame[:, :, ::-1].copy()
            height, width = rgb.shape[:2]
            image = QImage(rgb.data, width, height, width * 3, QImage.Format.Format_RGB888)
            self.frame.emit(image.copy(), detections)

            fps_cnt += 1
            elapsed = time.time() - fps_t
            if elapsed >= 1.0:
                self.fps_sig.emit(fps_cnt / elapsed, latency)
                fps_cnt = 0
                fps_t = time.time()

        self._running = False
        cap.release()


class ArduinoWorker(QThread):
    rx = pyqtSignal(str)
    status = pyqtSignal(bool, str)

    def __init__(self):
        super().__init__()
        self._q = queue.Queue()
        self._port = ""
        self._baud = 115200
        self._running = False
        self.ser = None

    def connect_to_port(self, port, baud=115200):
        if self.isRunning():
            self.status.emit(False, "Arduino already connected or connecting")
            return
        self._port = port
        self._baud = baud
        self.start()

    def send(self, cmd):
        self._q.put(cmd)

    def stop(self):
        self._running = False
        if self.ser and self.ser.is_open:
            self.ser.close()

    def run(self):
        try:
            self.ser = serial.Serial(self._port, self._baud, timeout=0.1)
            time.sleep(2)
            self.status.emit(True, f"Arduino @ {self._port} {self._baud}baud")
            self._running = True
            while self._running:
                if self.ser.in_waiting:
                    line = self.ser.readline().decode("utf-8", "replace").strip()
                    if line:
                        self.rx.emit(line)
                try:
                    cmd = self._q.get_nowait()
                    self.ser.write((cmd + "\n").encode())
                except queue.Empty:
                    pass
                time.sleep(0.01)
        except Exception as exc:
            self.status.emit(False, f"Arduino error: {exc}")
        finally:
            self._running = False
            if self.ser and self.ser.is_open:
                self.ser.close()
            self.ser = None
