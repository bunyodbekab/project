# SN74HC595N + ULN2803 + Relaylar ulanishi

## Komponentlar

1. **SN74HC595N** - 8-bitli Shift Register (16-pin DIP)
2. **ULN2803** - 8-kanalli Darlington Transistor Array (18-pin DIP)
3. **8 ta Relay modullari** (5V yoki 12V)

## SN74HC595N Ulanishi

### Orange Pi 3 Zero 4GB → SN74HC595N

| Orange Pi GPIO | SN74HC595N Pin | Funksiya | Config nomi |
|----------------|----------------|----------|-------------|
| GPIO 227       | 14 (DS)        | Data     | data_pin    |
| GPIO 75        | 11 (SHCP)      | Clock    | clock_pin   |
| GPIO 79        | 12 (STCP)      | Latch    | latch_pin   |

### SN74HC595N Quvvat ulanishi

| SN74HC595N Pin | Ulanish       |
|----------------|---------------|
| 16 (VCC)       | +5V           |
| 8 (GND)        | GND           |
| 13 (OE)        | GND (doimo faol) |
| 10 (SRCLR)     | +5V (reset o'chirilgan) |

## SN74HC595N → ULN2803 Ulanishi

| SN74HC595N Chiqish | ULN2803 Kirish | Servis    |
|--------------------|----------------|-----------|
| Q0 (Pin 15)        | Input 1        | KO'PIK    |
| Q1 (Pin 1)         | Input 2        | SUV       |
| Q2 (Pin 2)         | Input 3        | SHAMPUN   |
| Q3 (Pin 3)         | Input 4        | VOSK      |
| Q4 (Pin 4)         | Input 5        | PENA      |
| Q5 (Pin 5)         | Input 6        | OSMOS     |
| Q6 (Pin 6)         | Input 7        | QURITISH  |
| Q7 (Pin 7)         | Input 8        | (zaxira)  |

## ULN2803 → Relaylar

### ULN2803 Quvvat ulanishi

| ULN2803 Pin | Ulanish                    |
|-------------|----------------------------|
| Pin 9 (GND) | GND                        |
| Pin 10 (COM)| +12V (relay quvvati uchun) |

### Relay ulanishi

Har bir ULN2803 chiqishi (Output 1-8, Pin 18-11) bitta relay moduliga ulanadi:

- **ULN2803 Output** → **Relay IN piniga**
- **Relay VCC** → **+5V yoki +12V** (relay moduli uchun)
- **Relay GND** → **GND**

## Relay Chiqish Portlari

Har bir relay modulida quyidagi kontaktlar mavjud:
- **COM** (Common)
- **NO** (Normally Open)
- **NC** (Normally Closed)

Yuqori quvvatli yuklarni ulash:
- **COM** → Yukning bir tomoni
- **NO** → Yukning ikkinchi tomoni
- **Quvvat manbayi** → Yukning rejasiga muvofiq

## Texnik Ma'lumotlar

### SN74HC595N xususiyatlari
- Quvvat: 2V - 6V (5V tavsiya etiladi)
- Maksimal chiqish toki: 35mA
- Siljish tezligi: 100MHz gacha

### ULN2803 xususiyatlari
- Maksimal kuchlanish: 50V
- Maksimal tok: 500mA har bir kanal uchun
- Built-in diodlar (inductiv yuklarni himoya qilish uchun)

### Xavfsizlik

⚠️ **DIQQAT:**
1. Barcha ulanishlarni o'chirilgan holatda bajaring
2. Quvvat kuchlanishlarini to'g'ri tekshiring
3. ULN2803 issiq bo'lishi mumkin - sovutish ta'minlang
4. Yuqori quvvatli yuklar uchun qo'shimcha himoya kiriting

## Config faylini sozlash

`config.json` faylida shift register pinlarini o'zgartirish mumkin:

```json
{
  "shift_register": {
    "data_pin": 227,
    "clock_pin": 75,
    "latch_pin": 79
  },
  "services": {
    "KO'PIK": {
      "relay_bit": 0,
      ...
    }
  }
}
```

## Test qilish

1. Dasturni ishga tushiring
2. Har bir serverni ketma-ket bosib relay chertishini tekshiring
3. SN74HC595N chiqishlarini multimetr bilan o'lchang (0V yoki 5V)
4. ULN2803 chiqishlarini tekshiring
5. Relay kontaktlarining to'g'ri yopilishini tekshiring

## Muammolarni hal qilish

| Muammo | Sabab | Yechim |
|--------|-------|--------|
| Relay ishlamayapti | Noto'g'ri ulanish | Ulanishlarni qaytadan tekshiring |
| Barcha relaylar yoniq | Latch pin ulanmagan | Pin 12 ga latch_pin ulang |
| Tasodifiy signallar | Clock shovqini | Pull-down qarshilik qo'shing |
| ULN2803 issiq | Haddan tashqari tok | Relay moduli tokini tekshiring |

## Schema diagramma

```
Raspberry Pi                  SN74HC595N                ULN2803              Relay 1-8
                              ┌─────────┐
GPIO227 (DATA)  ────────────┤14 DS  Q0├15────────────┤IN1  OUT1├─────────► Relay 1 (KO'PIK)
GPIO75  (CLOCK) ────────────┤11 SHCP Q1├1─────────────┤IN2  OUT2├─────────► Relay 2 (SUV)
GPIO79  (LATCH) ────────────┤12 STCP Q2├2─────────────┤IN3  OUT3├─────────► Relay 3 (SHAMPUN)
                             │    ... Q3├3─────────────┤IN4  OUT4├─────────► Relay 4 (VOSK)
+5V ────────────────────────┤16 VCC  Q4├4─────────────┤IN5  OUT5├─────────► Relay 5 (PENA)
GND ────────────────────────┤8  GND  Q5├5─────────────┤IN6  OUT6├─────────► Relay 6 (OSMOS)
GND ────────────────────────┤13 OE   Q6├6─────────────┤IN7  OUT7├─────────► Relay 7 (QURITISH)
+5V ────────────────────────┤10 SRCLR Q7├7─────────────┤IN8  OUT8├─────────► Relay 8 (Zaxira)
                             └─────────┘               │         │
                                                       │GND  COM │
                                                  GND──┤9    10  ├──+12V
                                                       └─────────┘
```

Muvaffaqiyatlar! 🚀
