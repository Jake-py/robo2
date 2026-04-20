#include <Arduino.h>
#include <Servo.h>

namespace {
// Servo configuration
const int SERVO_MAX_DEG = 180;      // Maximum servo angle (degrees)
const int SERVO_MIN_US = 1000;      // Minimum servo pulse (microseconds, 0°)
const int SERVO_MAX_US = 2000;      // Maximum servo pulse (microseconds, 180°)

const int SERVO_COUNT = 14;
const int MOTOR_COUNT = 13;

struct ServoChannel {
  const char* id;
  uint8_t pin;
  Servo servo;
  bool powerEnabled;
  int currentAngle;
};

struct MotorChannel {
  const char* id;
  uint8_t pin;
  int currentSpeed;  // -255 to 255, negative for backward
};

ServoChannel channels[SERVO_COUNT] = {
  {"P0", 0, Servo(), true, 0},
  {"P1", 1, Servo(), true, 0},
  {"P2", 2, Servo(), true, 0},
  {"P3", 3, Servo(), true, 0},
  {"P4", 4, Servo(), true, 0},
  {"P5", 5, Servo(), true, 0},
  {"P6", 6, Servo(), true, 0},
  {"P7", 7, Servo(), true, 0},
  {"P8", 8, Servo(), true, 0},
  {"P9", 9, Servo(), true, 0},
  {"P10", 10, Servo(), true, 0},
  {"P11", 11, Servo(), true, 0},
  {"P12", 12, Servo(), true, 0},
  {"P13", 13, Servo(), true, 0},
};

MotorChannel motors[MOTOR_COUNT] = {
  {"P0", 0, 0},
  {"P1", 1, 0},
  {"P2", 2, 0},
  {"P3", 3, 0},
  {"P4", 4, 0},
  {"P5", 5, 0},
  {"P6", 6, 0},
  {"P7", 7, 0},
  {"P8", 8, 0},
  {"P9", 9, 0},
  {"P10", 10, 0},
  {"P11", 11, 0},
  {"P12", 12, 0},
};

String lineBuffer;
}  // namespace

int clampAngle(int value) {
  if (value < 0) return 0;
  if (value > SERVO_MAX_DEG) return SERVO_MAX_DEG;
  return value;
}

void writeServoAngle(ServoChannel& ch, int angle) {
  ch.currentAngle = clampAngle(angle);
  if (!ch.powerEnabled) return;
  int pulse = map(ch.currentAngle, 0, SERVO_MAX_DEG, SERVO_MIN_US, SERVO_MAX_US);
  ch.servo.writeMicroseconds(pulse);
}

void writeMotorSpeed(MotorChannel& m, int speed) {
  m.currentSpeed = constrain(speed, -255, 255);
  if (m.currentSpeed == 0) {
    analogWrite(m.pin, 0);
  } else {
    int pwm = abs(m.currentSpeed);
    analogWrite(m.pin, pwm);
  }
}

MotorChannel* getMotorById(const String& id) {
  for (int i = 0; i < MOTOR_COUNT; ++i) {
    if (id.equals(motors[i].id)) return &motors[i];
  }
  return nullptr;
}

void homeAllServos() {
  for (int i = 0; i < SERVO_COUNT; ++i) {
    writeServoAngle(channels[i], 0);
  }
}

ServoChannel* getChannelById(const String& id) {
  for (int i = 0; i < SERVO_COUNT; ++i) {
    if (id.equals(channels[i].id)) return &channels[i];
  }
  return nullptr;
}

void publishState(const ServoChannel& ch) {
  Serial.print("STATE:");
  Serial.print(ch.id);
  Serial.print(":PIN=");
  Serial.print(ch.pin);
  Serial.print(";ANGLE=");
  Serial.print(ch.currentAngle);
  Serial.print(";POWER=");
  Serial.println(ch.powerEnabled ? 1 : 0);
}

void publishAllStates() {
  for (int i = 0; i < SERVO_COUNT; ++i) {
    publishState(channels[i]);
  }
}

int parseIntStrict(const String& src, bool& ok) {
  String sub = src;
  sub.trim();
  if (sub.length() == 0) {
    ok = false;
    return 0;
  }
  for (int i = 0; i < sub.length(); ++i) {
    char c = sub.charAt(i);
    if (i == 0 && (c == '-' || c == '+')) continue;
    if (!isDigit(c)) {
      ok = false;
      return 0;
    }
  }
  ok = true;
  return sub.toInt();
}

bool handleServoAction(ServoChannel& ch, const String& action, const String& arg1) {
  if (action == "STATUS") {
    publishState(ch);
    return true;
  }
  if (action == "HOME") {
    writeServoAngle(ch, 0);
    Serial.print("OK:");
    Serial.print(ch.id);
    Serial.println(":HOME");
    publishState(ch);
    return true;
  }
  if (action == "SET") {
    bool ok = false;
    int angle = parseIntStrict(arg1, ok);
    if (!ok) {
      Serial.println("ERR:BAD_ANGLE");
      return true;
    }
    writeServoAngle(ch, angle);
    Serial.print("OK:");
    Serial.print(ch.id);
    Serial.println(":SET");
    publishState(ch);
    return true;
  }
  if (action == "POWER") {
    if (arg1 == "ON") {
      if (!ch.servo.attached()) {
        ch.servo.attach(ch.pin);
        delay(20);
      }
      ch.powerEnabled = true;
      writeServoAngle(ch, ch.currentAngle);
      Serial.print("OK:");
      Serial.print(ch.id);
      Serial.println(":POWER:ON");
      publishState(ch);
      return true;
    }
    if (arg1 == "OFF") {
      ch.powerEnabled = false;
      if (ch.servo.attached()) {
        ch.servo.detach();
      }
      Serial.print("OK:");
      Serial.print(ch.id);
      Serial.println(":POWER:OFF");
      publishState(ch);
      return true;
    }
    Serial.println("ERR:BAD_POWER");
    return true;
  }
  return false;
}

bool handleMotorAction(MotorChannel& m, const String& action, const String& arg1) {
  if (action == "fwd") {
    bool ok = false;
    int speed = parseIntStrict(arg1, ok);
    if (!ok || speed < 0 || speed > 255) {
      Serial.println("ERR:BAD_SPEED");
      return true;
    }
    writeMotorSpeed(m, speed);
    Serial.print("OK:");
    Serial.print(m.id);
    Serial.println(":fwd");
    return true;
  }
  if (action == "bkwd") {
    bool ok = false;
    int speed = parseIntStrict(arg1, ok);
    if (!ok || speed < 0 || speed > 255) {
      Serial.println("ERR:BAD_SPEED");
      return true;
    }
    writeMotorSpeed(m, -speed);
    Serial.print("OK:");
    Serial.print(m.id);
    Serial.println(":bkwd");
    return true;
  }
  if (action == "stop") {
    writeMotorSpeed(m, 0);
    Serial.print("OK:");
    Serial.print(m.id);
    Serial.println(":stop");
    return true;
  }
  return false;
}

void handleMotorCommand(const String& cmd) {
  // Format: MOTOR:<ID>:<ACTION>:<ARG1>
  int p1 = cmd.indexOf(':', 6);
  int p2 = (p1 >= 0) ? cmd.indexOf(':', p1 + 1) : -1;
  int p3 = (p2 >= 0) ? cmd.indexOf(':', p2 + 1) : -1;

  if (p1 < 0 || p2 < 0) {
    Serial.println("ERR:BAD_FORMAT");
    return;
  }

  String id = cmd.substring(6, p1);
  String action = cmd.substring(p1 + 1, p2);
  String arg1 = (p3 >= 0) ? cmd.substring(p2 + 1, p3) : cmd.substring(p2 + 1);
  id.trim();
  action.trim();
  arg1.trim();

  MotorChannel* m = getMotorById(id);
  if (!m) {
    Serial.println("ERR:BAD_MOTOR_ID");
    return;
  }
  if (!handleMotorAction(*m, action, arg1)) {
    Serial.println("ERR:UNKNOWN_MOTOR_ACTION");
  }
}

void handleServoCommand(const String& cmd) {
  // Format: SERVO:<ID|ALL>:<ACTION>[:ARG1]
  int p1 = cmd.indexOf(':', 6);
  int p2 = (p1 >= 0) ? cmd.indexOf(':', p1 + 1) : -1;
  int p3 = (p2 >= 0) ? cmd.indexOf(':', p2 + 1) : -1;

  if (p1 < 0) {
    Serial.println("ERR:BAD_FORMAT");
    return;
  }

  String id = cmd.substring(6, p1);
  String action = (p2 >= 0) ? cmd.substring(p1 + 1, p2) : cmd.substring(p1 + 1);
  String arg1 = (p2 >= 0) ? ((p3 >= 0) ? cmd.substring(p2 + 1, p3) : cmd.substring(p2 + 1)) : "";
  id.trim();
  action.trim();
  arg1.trim();

  if (id == "ALL") {
    if (action == "HOME") {
      homeAllServos();
      Serial.println("OK:ALL:HOME");
      publishAllStates();
      return;
    }
    if (action == "STATUS") {
      publishAllStates();
      return;
    }
    Serial.println("ERR:BAD_ALL_ACTION");
    return;
  }

  ServoChannel* ch = getChannelById(id);
  if (!ch) {
    Serial.println("ERR:BAD_SERVO_ID");
    return;
  }
  if (!handleServoAction(*ch, action, arg1)) {
    Serial.println("ERR:UNKNOWN_SERVO_ACTION");
  }
}

void handleCommand(String cmd) {
  cmd.trim();
  if (cmd.length() == 0) return;

  if (cmd == "HELLO" || cmd == "PING") {
    Serial.println("PONG:RIGHT_HAND_SERVO");
    publishAllStates();
    return;
  }
  if (cmd == "STATUS") {
    publishAllStates();
    return;
  }
  if (cmd.startsWith("SERVO:")) {
    handleServoCommand(cmd);
    return;
  }
  if (cmd.startsWith("MOTOR:")) {
    handleMotorCommand(cmd);
    return;
  }

  Serial.println("ERR:UNKNOWN_CMD");
}

void setup() {
  Serial.begin(115200);
  for (int i = 0; i < SERVO_COUNT; ++i) {
    channels[i].servo.attach(channels[i].pin);
  }
  for (int i = 0; i < MOTOR_COUNT; ++i) {
    pinMode(motors[i].pin, OUTPUT);
  }
  homeAllServos();
  Serial.println("READY:RIGHT_HAND_SERVO");
  publishAllStates();
}

void loop() {
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\r') continue;
    if (c == '\n') {
      handleCommand(lineBuffer);
      lineBuffer = "";
    } else {
      lineBuffer += c;
      if (lineBuffer.length() > 120) {
        lineBuffer = "";
        Serial.println("ERR:CMD_TOO_LONG");
      }
    }
  }
}
