# TODO: Qt Servo + Wheels (Колеса) Motors GUI + Arduino

Previous tasks complete.

## Wheels (Колеса) - NEW TASK (Approved ✅)

Add motor control tab mirroring servos:
- Pins 0-12 checkboxes (multi-select)
- Shared speed 0-255
- Buttons: ВПЕРЁД/НАЗАД/СТОП (on selected pins)
- Commands: MOTOR:PID:dir:speed (fwd/bkwd/stop:0)

### Steps:
1. ✅ Plan confirmed
2. ✅ TODO.md created/updated (this file)
3. ✅ Edit robo_center_app/main_window.py (WHEEL_PINS, _wheel_widgets, full _tab_wheels() + handlers)
4. ☐ Test UI: `python3 robo_center.py` → verify Колеса tab (checkboxes, slider, buttons)
5. ☐ Test cmds: Connect Arduino → buttons send MOTOR: cmds (check serial)
6. ☐ Update arduino_dual_servo.ino for MOTOR: handler if needed
7. ☐ Add wheels support for Arduino Uno with pins 0-12 in mg996r_hand_qt.py
8. ☐ Verify wheels and pins work properly (standard operation)
9. ☐ Implement control for each wheel pin, add selection for simultaneous control of selected pins
10. ☐ Complete & demo

## Old:
- Servo GUI done (ПРАВАЯ РУКА tab)
- Arduino refactor pending (add MOTOR support later)
