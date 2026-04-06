"""Background workers for SSH, video and serial device handling."""

import glob
import os
import queue
import time

import paramiko
import requests
import serial
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QImage


# ---------------------------------------------------------------------------
# YOLO model registry — all known Ultralytics model families
# ---------------------------------------------------------------------------
YOLO_MODEL_PRESETS = [
    # YOLOv8 family
    "yolov8n.pt", "yolov8s.pt", "yolov8m.pt", "yolov8l.pt", "yolov8x.pt",
    # YOLOv8 segmentation
    "yolov8n-seg.pt", "yolov8s-seg.pt", "yolov8m-seg.pt", "yolov8l-seg.pt",
    # YOLOv8 pose
    "yolov8n-pose.pt", "yolov8s-pose.pt", "yolov8m-pose.pt",
    # YOLO11 family
    "yolo11n.pt", "yolo11s.pt", "yolo11m.pt", "yolo11l.pt", "yolo11x.pt",
    # YOLO11 segmentation
    "yolo11n-seg.pt", "yolo11s-seg.pt", "yolo11m-seg.pt",
    # YOLO11 pose
    "yolo11n-pose.pt", "yolo11s-pose.pt", "yolo11m-pose.pt",
    # YOLOv9 family
    "yolov9c.pt", "yolov9e.pt",
    # YOLOv10 family
    "yolov10n.pt", "yolov10s.pt", "yolov10m.pt", "yolov10l.pt", "yolov10x.pt",
]

# Human-readable labels for known models
YOLO_MODEL_LABELS = {
    "yolov8n.pt": "YOLOv8n  · Nano  · 3.2M",
    "yolov8s.pt": "YOLOv8s  · Small · 11M",
    "yolov8m.pt": "YOLOv8m  · Med   · 25M",
    "yolov8l.pt": "YOLOv8l  · Large · 43M",
    "yolov8x.pt": "YOLOv8x  · XL    · 68M",
    "yolov8n-seg.pt": "YOLOv8n-seg  · Nano",
    "yolov8s-seg.pt": "YOLOv8s-seg  · Small",
    "yolov8m-seg.pt": "YOLOv8m-seg  · Med",
    "yolov8l-seg.pt": "YOLOv8l-seg  · Large",
    "yolov8n-pose.pt": "YOLOv8n-pose · Nano",
    "yolov8s-pose.pt": "YOLOv8s-pose · Small",
    "yolov8m-pose.pt": "YOLOv8m-pose · Med",
    "yolo11n.pt": "YOLO11n  · Nano  · 2.6M",
    "yolo11s.pt": "YOLO11s  · Small · 9.4M",
    "yolo11m.pt": "YOLO11m  · Med   · 20M",
    "yolo11l.pt": "YOLO11l  · Large · 25M",
    "yolo11x.pt": "YOLO11x  · XL    · 56M",
    "yolo11n-seg.pt": "YOLO11n-seg  · Nano",
    "yolo11s-seg.pt": "YOLO11s-seg  · Small",
    "yolo11m-seg.pt": "YOLO11m-seg  · Med",
    "yolo11n-pose.pt": "YOLO11n-pose · Nano",
    "yolo11s-pose.pt": "YOLO11s-pose · Small",
    "yolo11m-pose.pt": "YOLO11m-pose · Med",
    "yolov9c.pt": "YOLOv9c  · Compact",
    "yolov9e.pt": "YOLOv9e  · Extended",
    "yolov10n.pt": "YOLOv10n · Nano",
    "yolov10s.pt": "YOLOv10s · Small",
    "yolov10m.pt": "YOLOv10m · Med",
    "yolov10l.pt": "YOLOv10l · Large",
    "yolov10x.pt": "YOLOv10x · XL",
}


def scan_local_models(search_dirs=None):
    """
    Scan directories for .pt model files.
    Returns list of (filename, label, full_path) tuples.
    """
    if search_dirs is None:
        search_dirs = [
            ".",
            os.path.expanduser("~"),
            os.path.expanduser("~/.cache/ultralytics"),
            os.path.expanduser("~/ultralytics"),
        ]

    found = {}  # filename -> full_path (deduplicate)
    for directory in search_dirs:
        for path in glob.glob(os.path.join(directory, "*.pt")):
            name = os.path.basename(path)
            if name not in found:
                found[name] = path

    # Build result: local files first, then presets not found locally
    result = []
    # Local files
    for name, path in sorted(found.items()):
        label = YOLO_MODEL_LABELS.get(name, name)
        result.append((name, f"[LOCAL] {label}", path))

    # Known presets not yet downloaded
    for preset in YOLO_MODEL_PRESETS:
        if preset not in found:
            label = YOLO_MODEL_LABELS.get(preset, preset)
            result.append((preset, f"[AUTO-DL] {label}", preset))

    return result


# ---------------------------------------------------------------------------
# LocalYoloEngine — single model instance
# ---------------------------------------------------------------------------

class LocalYoloEngine:
    def __init__(self):
        self.model = None
        self.model_name = ""
        self.model_ref = ""
        self.device = "cpu"
        self.enabled = True  # soft on/off without unloading

    @property
    def is_ready(self):
        return self.model is not None and self.enabled

    def load(self, model_name="yolo11s.pt", device="cpu"):
        try:
            from ultralytics import YOLO
        except ImportError as exc:
            raise RuntimeError("ultralytics not installed. pip install ultralytics") from exc
        self.model = YOLO(model_name)
        self.model_ref = model_name
        self.model_name = os.path.basename(model_name)
        self.device = device
        self.enabled = True

    def unload(self):
        self.model = None
        self.model_name = ""
        self.model_ref = ""
        self.device = "cpu"
        self.enabled = True

    def enable(self):
        self.enabled = True

    def disable(self):
        self.enabled = False

    def infer_frame(self, frame, mode="detect", conf=0.25):
        if not self.model:
            raise RuntimeError("Model not loaded")
        if not self.enabled:
            return []

        if mode == "track":
            results = self.model.track(
                frame, conf=conf, persist=True, verbose=False, device=self.device
            )
        elif mode == "segment":
            results = self.model.predict(
                frame, conf=conf, task="segment", verbose=False, device=self.device
            )
        else:
            results = self.model.predict(
                frame, conf=conf, verbose=False, device=self.device
            )

        return self._parse_results(results)

    def _parse_results(self, results):
        detections = []
        if not results:
            return detections
        result = results[0]
        boxes = getattr(result, "boxes", None)
        if boxes is None:
            return detections
        names = result.names or {}
        for i in range(len(boxes)):
            xyxy = boxes.xyxy[i].tolist()
            conf_val = float(boxes.conf[i]) if boxes.conf is not None else 0.0
            cls_id = int(boxes.cls[i]) if boxes.cls is not None else -1
            name = names.get(cls_id, str(cls_id))
            tid = None
            if hasattr(boxes, "id") and boxes.id is not None:
                try:
                    tid = int(boxes.id[i])
                except Exception:
                    tid = None
            detections.append({
                "box": xyxy,
                "class_name": name,
                "confidence": conf_val,
                "track_id": tid,
            })
        return detections


# ---------------------------------------------------------------------------
# YoloModelManager — manages a pool of named engines
# ---------------------------------------------------------------------------

class YoloModelManager:
    """
    Manages multiple LocalYoloEngine instances by slot name.
    Provides active engine selection and enable/disable per slot.
    """

    SLOTS = ["PRIMARY", "SECONDARY", "TERTIARY"]

    def __init__(self):
        self._engines: dict[str, LocalYoloEngine] = {
            slot: LocalYoloEngine() for slot in self.SLOTS
        }
        self._active_slot = "PRIMARY"

    def engine(self, slot: str) -> LocalYoloEngine:
        return self._engines[slot]

    def active_engine(self) -> LocalYoloEngine:
        return self._engines[self._active_slot]

    def active_slot(self) -> str:
        return self._active_slot

    def set_active(self, slot: str):
        if slot in self._engines:
            self._active_slot = slot

    def load(self, slot: str, model_name: str, device: str = "cpu"):
        self._engines[slot].load(model_name, device)

    def unload(self, slot: str):
        self._engines[slot].unload()

    def enable(self, slot: str):
        self._engines[slot].enable()

    def disable(self, slot: str):
        self._engines[slot].disable()

    def is_ready(self, slot: str) -> bool:
        return self._engines[slot].is_ready

    def any_ready(self) -> bool:
        return any(e.is_ready for e in self._engines.values())

    def status_summary(self) -> dict:
        return {
            slot: {
                "loaded": eng.model is not None,
                "enabled": eng.enabled,
                "model": eng.model_name,
                "device": eng.device,
                "active": slot == self._active_slot,
            }
            for slot, eng in self._engines.items()
        }


# ---------------------------------------------------------------------------
# LocalOcrEngine — pytesseract OCR helper
# ---------------------------------------------------------------------------

class LocalOcrEngine:
    def __init__(self, lang="eng", min_conf=50):
        self.lang = lang
        self.min_conf = min_conf
        self.enabled = True
        self._version = None

    @property
    def is_ready(self):
        try:
            import pytesseract
            self._version = str(pytesseract.get_tesseract_version())
            return self.enabled
        except Exception:
            return False

    def infer_frame(self, frame, lang=None, min_conf=None):
        if not self.enabled:
            return []
        try:
            import cv2
            import pytesseract
            from pytesseract import Output
        except ImportError as exc:
            raise RuntimeError("pytesseract/opencv not installed") from exc

        lang = lang or self.lang
        min_conf = self.min_conf if min_conf is None else min_conf

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        data = pytesseract.image_to_data(gray, lang=lang, output_type=Output.DICT)

        items = []
        count = len(data.get("text", []))
        for i in range(count):
            raw_text = (data["text"][i] or "").strip()
            try:
                conf = float(data["conf"][i])
            except Exception:
                conf = -1.0
            if not raw_text or conf < min_conf:
                continue
            x = int(data["left"][i])
            y = int(data["top"][i])
            w = int(data["width"][i])
            h = int(data["height"][i])
            items.append({
                "text": raw_text,
                "confidence": conf,
                "box": [x, y, x + w, y + h],
            })
        return items


# ---------------------------------------------------------------------------
# SSH Worker
# ---------------------------------------------------------------------------

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
                self._host, port=self._port,
                username=self._user, password=self._pwd, timeout=10,
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


# ---------------------------------------------------------------------------
# YOLO Stream Worker
# ---------------------------------------------------------------------------

class YoloStream(QThread):
    frame = pyqtSignal(QImage, list, list)
    fps_sig = pyqtSignal(float, float)
    err = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._server = ""
        self._src = 0
        self._mode = "detect"
        self._conf = 0.25
        self._backend = "remote"
        self._local_engine = None
        self._ocr_engine = None
        self._ocr_enabled = False
        self._ocr_lang = "eng"
        self._running = False
        self._request_error_emitted = False

    def set_backend(self, backend, local_engine=None, ocr_engine=None, ocr_enabled=False, ocr_lang="eng"):
        self._backend = backend
        self._local_engine = local_engine
        self._ocr_engine = ocr_engine
        self._ocr_enabled = ocr_enabled
        self._ocr_lang = ocr_lang or "eng"

    def start_stream(self, server, src, mode, conf=0.25):
        if self.isRunning():
            self.err.emit("Vision stream already running")
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

            detections = []
            ocr_items = []
            t0 = time.time()
            if self._backend == "local":
                if not self._local_engine or not self._local_engine.is_ready:
                    self.err.emit("Local AI not loaded or disabled")
                    break
                try:
                    detections = self._local_engine.infer_frame(frame, self._mode, self._conf)
                    latency = (time.time() - t0) * 1000
                    self._request_error_emitted = False
                except Exception as exc:
                    latency = 0.0
                    if not self._request_error_emitted:
                        self.err.emit(f"Local AI error: {exc}")
                        self._request_error_emitted = True
                if self._ocr_enabled and self._ocr_engine and self._ocr_engine.is_ready:
                    try:
                        ocr_items = self._ocr_engine.infer_frame(frame, lang=self._ocr_lang)
                    except Exception as exc:
                        if not self._request_error_emitted:
                            self.err.emit(f"OCR error: {exc}")
                            self._request_error_emitted = True
            else:
                _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
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
                except Exception as exc:
                    latency = 0.0
                    if not self._request_error_emitted:
                        self.err.emit(f"Vision request error: {exc}")
                        self._request_error_emitted = True

            if detections:
                self._draw_detections(frame, detections)
            if ocr_items:
                self._draw_ocr(frame, ocr_items)

            rgb = frame[:, :, ::-1].copy()
            height, width = rgb.shape[:2]
            image = QImage(rgb.data, width, height, width * 3, QImage.Format.Format_RGB888)
            self.frame.emit(image.copy(), detections, ocr_items)

            fps_cnt += 1
            elapsed = time.time() - fps_t
            if elapsed >= 1.0:
                self.fps_sig.emit(fps_cnt / elapsed, latency)
                fps_cnt = 0
                fps_t = time.time()

        self._running = False
        cap.release()

    def _draw_detections(self, frame, detections):
        import cv2
        for det in detections:
            box = det.get("box", [0, 0, 0, 0])
            x1, y1, x2, y2 = map(int, box)
            name = det.get("class_name", "?")
            conf = det.get("confidence", 0.0)
            tid = det.get("track_id")
            label = f"{name} {conf:.2f}" + (f" #{tid}" if tid is not None else "")
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 229, 255), 2)
            cv2.rectangle(frame, (x1, y1 - 18), (x1 + len(label) * 7, y1), (0, 229, 255), -1)
            cv2.putText(frame, label, (x1 + 2, y1 - 4),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (4, 6, 10), 1)

    def _draw_ocr(self, frame, ocr_items):
        import cv2
        for item in ocr_items:
            x1, y1, x2, y2 = map(int, item.get("box", [0, 0, 0, 0]))
            text = item.get("text", "")
            conf = item.get("confidence", 0.0)
            label = f"OCR {text} {conf:.0f}"
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 157), 1)
            top = max(0, y1 - 18)
            cv2.rectangle(frame, (x1, top), (x1 + min(len(label) * 7, 220), y1), (0, 255, 157), -1)
            cv2.putText(frame, label[:28], (x1 + 2, max(12, y1 - 4)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (4, 6, 10), 1)


# ---------------------------------------------------------------------------
# Arduino Worker
# ---------------------------------------------------------------------------

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
