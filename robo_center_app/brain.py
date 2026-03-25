"""Robot behavior controller."""

import time


class RobotBrain:
    """Simple rule-based AI controller."""

    def __init__(self, on_cmd):
        self._cmd = on_cmd
        self._mode = "IDLE"
        self._target_class = "person"
        self._last_cmd = ""
        self._last_t = 0.0
        self._cooldown = 0.3
        self._avoid_until = 0.0

    def set_mode(self, mode):
        self._mode = mode
        if mode != "AVOID":
            self._avoid_until = 0.0

    def set_target(self, cls):
        self._target_class = cls

    def process(self, detections, frame_w=640, frame_h=480):
        now = time.time()
        if now - self._last_t < self._cooldown:
            return
        self._last_t = now

        if self._mode == "IDLE":
            return

        if self._mode == "FOLLOW":
            self._process_follow(detections, frame_w, frame_h)
            return

        if self._mode == "PATROL":
            self._send("MOVE:LEFT:120" if detections else "MOVE:FORWARD:150")
            return

        if self._mode == "AVOID":
            self._process_avoid(detections, now)
            return

        if self._mode == "GUARD":
            humans = [d for d in detections if d.get("class_name") == "person"]
            self._send("ALERT:INTRUDER:1" if humans else "ALERT:CLEAR:0")

    def _process_follow(self, detections, frame_w, frame_h):
        targets = [d for d in detections if d.get("class_name") == self._target_class]
        if not targets:
            self._send("MOVE:STOP:0")
            return

        best = max(targets, key=lambda d: d.get("confidence", 0.0))
        box = best.get("box", [0, 0, 0, 0])
        cx = (box[0] + box[2]) / 2
        area = (box[2] - box[0]) * (box[3] - box[1]) / (frame_w * frame_h)

        if area > 0.4:
            self._send("MOVE:BACKWARD:80")
        elif area < 0.05:
            self._send("MOVE:FORWARD:150")
        elif cx < frame_w * 0.38:
            self._send("MOVE:LEFT:100")
        elif cx > frame_w * 0.62:
            self._send("MOVE:RIGHT:100")
        else:
            self._send("MOVE:STOP:0")

    def _process_avoid(self, detections, now):
        if detections:
            self._send("MOVE:BACKWARD:100")
            self._avoid_until = now + 0.3
            return

        if self._avoid_until and now < self._avoid_until:
            self._send("MOVE:LEFT:120")
            return

        self._avoid_until = 0.0
        self._send("MOVE:FORWARD:130")

    def _send(self, cmd):
        if cmd != self._last_cmd:
            self._last_cmd = cmd
            self._cmd(cmd)

