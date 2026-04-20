# MG996R Control Notes
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIC3Hy8QZqTm6cElFPGCFYE58gGb2MX+koZbiSV63awe5 red_ice@tds_server
## Что используется для отправки сигнала

В проекте управление идет по `Serial` (USB-UART) между Python GUI и Arduino:

- GUI: `mg996r_hand_qt.py` (PyQt6 + pyserial)
- Прошивка: `arduino_dual_servo/arduino_dual_servo.ino`
- Скорость порта: `115200` (по умолчанию)

Python отправляет текстовые команды в Arduino, каждая команда завершается `\n`.

Пример:

```text
POWER:ON
HOME
STEP:5
SMART:ON
CAL:RANGE:0:360
STATUS
```

---

## Как сейчас управляется сервопривод

Схема:

1. GUI открывает COM-порт (`/dev/ttyACM*` или `/dev/ttyUSB*`).
2. Отправляет команды в Arduino.
3. Arduino парсит команды и управляет `Servo` через:
   - `writeMicroseconds(...)` (диапазон импульса сейчас `500..2500` мкс)
4. Arduino отправляет ответ/состояние в виде строки `STATE:...`.

Текущие ключевые команды:

- `POWER:ON` / `POWER:OFF` — включить/отключить удержание серво (detach/attach)
- `HOME` — вернуть в `0°`
- `STEP:<delta>` — пошаговое движение (сейчас кнопки Left/Right дают `±5°`)
- `SMART:ON` / `SMART:OFF` — включить/выключить smart режим
- `CAL:RANGE:<min>:<max>` — задать рабочий диапазон
- `STATUS` / `PING` / `HELLO` — диагностика

Состояние от Arduino:

```text
STATE:ANGLE=...;MIN=...;MAX=...;RADIUS=...;SMART=...;POWER=...
```

---

## Как добавить много сервоприводов в будущем

Рекомендуемый подход:

1. Ввести адресацию серв в протоколе:
   - формат команды: `SERVO:<id>:<action>:<value>`
   - пример: `SERVO:2:SET:120`, `SERVO:5:STEP:-5`, `SERVO:1:POWER:OFF`

2. На Arduino хранить массив/таблицу серв:
   - `Servo servos[N]`
   - массив текущих углов, min/max, power-state для каждого `id`

3. Для каждого серво хранить отдельную конфигурацию:
   - `pin`, `min_deg`, `max_deg`, `min_us`, `max_us`

4. Разнести логику:
   - модуль парсинга команд
   - модуль управления каналом серво
   - модуль телеметрии состояния

5. В GUI:
   - добавить список сервоприводов (`id`)
   - отдельные кнопки/статус по каждому каналу
   - периодический `STATUS:ALL`

6. Для большого числа серв:
   - использовать драйвер PWM (`PCA9685`) вместо прямого управления только пинами Arduino
   - протокол оставить тем же, но backend сделать через PCA9685

---

## Важное ограничение по MG996R

Типичный MG996R обычно имеет механический ход около `180°`.
Даже если в коде разрешен диапазон до `360`, реальный угол зависит от конкретного привода и механики.
Перед эксплуатацией лучше калибровать безопасные `min/max` и не выходить за физические пределы.

---

## Инструкция по запуску

1. Перейти в корень проекта:

```bash
cd /home/red/projects/robo2
```

2. Установить зависимости Python:

```bash
python3 -m pip install PyQt6 pyserial
```

3. Установить `arduino-cli` (если не установлен) и ядро для Uno:

```bash
arduino-cli core update-index
arduino-cli core install arduino:avr
```

4. Подключить Arduino Uno по USB и проверить, что появился порт:

```bash
ls -l /dev/ttyACM* /dev/ttyUSB*
```

5. Прошить плату (пример для `/dev/ttyACM0`):

```bash
arduino-cli compile --fqbn arduino:avr:uno /home/red/projects/robo2/arduino_dual_servo
arduino-cli upload -p /dev/ttyACM0 --fqbn arduino:avr:uno /home/red/projects/robo2/arduino_dual_servo
```

6. Запустить GUI:

```bash
python3 /home/red/projects/robo2/mg996r_hand_qt.py
```

7. В GUI:
- нажать `Refresh`
- выбрать порт `/dev/ttyACM*` или `/dev/ttyUSB*`
- нажать `Connect`
- проверить кнопки `Power`, `Home`, `Left`, `Right`

8. Если порт не виден:
- добавить пользователя в группу `dialout`

```bash
sudo usermod -aG dialout $USER
```

- выйти/зайти в сессию и повторить шаги 4-7.
