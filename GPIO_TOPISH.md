# Orange Pi 3 Zero GPIO Pinlarni Topish

## 📌 Loyihada Ishlatiladigan GPIO Pinlar

### Chiqish (OUTPUT) - Shift Register uchun:
- **GPIO 227** - Data pin (SN74HC595N DS)
- **GPIO 75** - Clock pin (SN74HC595N SHCP)
- **GPIO 79** - Latch pin (SN74HC595N STCP)

### Kirish (INPUT) - Tugmalar uchun:
- **GPIO 229** - KO'PIK
- **GPIO 228** - SUV
- **GPIO 73** - SHAMPUN
- **GPIO 70** - VOSK
- **GPIO 72** - PENA
- **GPIO 231** - OSMOS
- **GPIO 232** - QURITISH
- **GPIO 230** - STOP

## 🔍 GPIO Pinlarni Qanday Topish

### 1-usul: `gpioinfo` buyrug'i

Terminal orqali quyidagi buyruqni bajaring:

```bash
sudo gpioinfo
```

Bu barcha GPIO chiplar va ularning line raqamlarini ko'rsatadi. `gpiochip1` bo'limini qidiring va kerakli GPIO raqamlarini toping.

### 2-usul: `gpio readall` (wiringPi o'xshash)

Agar Orange Pi uchun `wiringOP` o'rnatilgan bo'lsa:

```bash
sudo gpio readall
```

Bu jadvalni ko'rsatadi - GPIO raqamlari, fizik pin raqamlari va holatlarni.

### 3-usul: Qo'lda tekshirish

Har bir GPIO ni sysfs orqali tekshirish:

```bash
# GPIO export qilish
echo 227 > /sys/class/gpio/export

# Papkada mavjudligini tekshirish
ls /sys/class/gpio/gpio227/

# Tozalash
echo 227 > /sys/class/gpio/unexport
```

## 📍 Orange Pi 3 Zero 40-Pin GPIO Header

```
    3.3V  [ 1] [ 2]  5V
  GPIO12  [ 3] [ 4]  5V
  GPIO11  [ 5] [ 6]  GND
  GPIO 6  [ 7] [ 8]  GPIO13
     GND  [ 9] [10]  GPIO14
  GPIO 1  [11] [12]  GPIO110
  GPIO 0  [13] [14]  GND
  GPIO 3  [15] [16]  GPIO19
    3.3V  [17] [18]  GPIO18
  GPIO64  [19] [20]  GND
  GPIO65  [21] [22]  GPIO 2
  GPIO66  [23] [24]  GPIO67
     GND  [25] [26]  GPIO21
  GPIO19  [27] [28]  GPIO20
   GPIO7  [29] [30]  GND
   GPIO8  [31] [32]  GPIO200
   GPIO9  [33] [34]  GND
  GPIO10  [35] [36]  GPIO107
  GPIO17  [37] [38]  GPIO15
     GND  [39] [40]  GPIO16
```

## 🔌 GPIO Line Raqamlarini Hisoblash

Orange Pi da GPIO line raqami quyidagicha hisoblanadi:

**GPIO Line = (Port × 32) + Pin**

Masalan:
- **PA12** = (0 × 32) + 12 = **12**
- **PC7** = (2 × 32) + 7 = **71**
- **PG11** = (6 × 32) + 11 = **203**

Port nomlari:
- PA = 0
- PB = 1
- PC = 2
- PD = 3
- PE = 4
- PF = 5
- PG = 6
- PH = 7

## 🛠️ Pinlarni Tekshirish Skripti

Quyidagi Python skriptni yarating va bajaring:

```python
import gpiod

chip = gpiod.Chip("gpiochip1")

# Bizning pinlarimiz
pins_to_check = [227, 75, 79, 229, 228, 73, 70, 72, 231, 232, 230]

print("GPIO Pin Tekshiruvi:\n")
print(f"{'Line':<6} {'Consumer':<20} {'Direction':<10} {'Active'}")
print("-" * 50)

for pin in pins_to_check:
    try:
        line = chip.get_line(pin)
        info = line.consumer() if line.is_used() else "-"
        direction = "INPUT" if line.direction() == gpiod.Line.DIRECTION_INPUT else "OUTPUT"
        active = "Yes" if line.is_used() else "No"
        print(f"{pin:<6} {info:<20} {direction:<10} {active}")
    except Exception as e:
        print(f"{pin:<6} ERROR: {e}")

chip.close()
```

Faylni `check_gpio.py` deb saqlang va bajaring:

```bash
sudo python3 check_gpio.py
```

## ⚠️ Muhim Eslatmalar

1. **GPIO raqamlari qurilmaga bog'liq** - Har bir Orange Pi modelida farq qilishi mumkin
2. **Root huquqi kerak** - GPIO bilan ishlash uchun `sudo` ishlating
3. **Pin zararlanmasligi uchun** - Ulashdan oldin voltajni tekshiring (3.3V)
4. **Pull-up/Pull-down** - Input pinlar uchun kerak bo'lishi mumkin

## 🧪 Test Qilish

GPIO 227 ni test qilish uchun:

```python
import gpiod
import time

chip = gpiod.Chip("gpiochip1")
line = chip.get_line(227)
line.request(consumer="test", type=gpiod.LINE_REQ_DIR_OUT, default_vals=[0])

# LED yoki multimetr bilan tekshiring
print("GPIO 227 ni HIGH ga o'tkazyapman...")
line.set_value(1)
time.sleep(2)
print("GPIO 227 ni LOW ga o'tkazyapman...")
line.set_value(0)

chip.close()
```

## 📞 Yordam

Agar pinlarni topa olmasangiz, quyidagilarni bajaring:

1. Orange Pi 3 Zero pinout diagrammasini qidiring
2. `gpioinfo` chiqishini to'liq tekshiring
3. Datasheet dan kerakli pinlarni aniqlang
4. Multimetr bilan fizik tekshiruv o'tkazing

---

**Eslatma**: Yuqoridagi GPIO raqamlari (227, 75, 79, va h.k.) Orange Pi 3 Zero uchun to'g'ri ekanligini `gpioinfo` orqali tekshiring!
