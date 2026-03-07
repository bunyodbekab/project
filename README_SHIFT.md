# Shift Register bilan Relay boshqaruvi

Loyiha SN74HC595N shift register va ULN2803 transistor array yordamida relelarni boshqarish uchun yangilandi.

## O'zgarishlar

### Avvalgi usul
- Har bir relay uchun alohida GPIO pin kerak edi
- 7 ta relay = 7 ta GPIO pin

### Yangi usul
- Faqat 3 ta GPIO pin bilan 8 tagacha relayni boshqarish mumkin
- SN74HC595N shift register orqali
- ULN2803 relay driver bilan

## Afzalliklari

✅ **GPIO pinlarni tejash** - 7 ta pin o'rniga 3 ta pin ishlatiladi  
✅ **Kengaytirish imkoniyati** - Qo'shimcha shift registerlarni zanjirlab 16, 24 yoki undan ko'p relay boshqarish mumkin  
✅ **Sodda sim ulanishi** - Kamroq sim, sodda montaj  
✅ **Ishonchlilik** - ULN2803 relay uchun maxsus driver  

## Kerakli Komponentlar

1. **SN74HC595N** - 8-bit shift register IC (16-pin DIP)
2. **ULN2803** - 8-channel darlington array (18-pin DIP)
3. **8 ta relay modullar** (5V yoki 12V)
4. **Simlar** va ulanish uchun qismlar

## Ulanish

Batafsil ulanish sxemasi `ULANISH.md` faylida mavjud.

### Qisqacha:

```
Raspberry Pi → SN74HC595N → ULN2803 → Relay modullari
   (3 pin)      (shift reg)   (driver)    (8 relay)
```

## Konfiguratsiya

`config.json` fayli yangilandi:

```json
{
  "shift_register": {
    "data_pin": 227,    // SN74HC595N DS (14-pin)
    "clock_pin": 75,    // SN74HC595N SHCP (11-pin)  
    "latch_pin": 79     // SN74HC595N STCP (12-pin)
  },
  "services": {
    "KO'PIK": {
      "relay_bit": 0,   // relay raqami (0-7)
      ...
    }
  }
}
```

## Test qilish

Shift register to'g'ri ishlayotganini tekshirish uchun:

```bash
python3 test_shift_register.py
```

Bu dastur:
- Barcha relelarni yoqadi/o'chiradi
- Har bir releni alohida test qiladi
- Turli naqshlarni ko'rsatadi
- Yuguruvchi chiroq effektini ko'rsatadi

## Asosiy dasturni ishga tushirish

```bash
python3 main.py
```

## Muammolarni hal qilish

### Relaylar ishlamayapti
1. Ulanishlarni tekshiring (ULANISH.md ga qarang)
2. Test dasturini ishga tushiring: `python3 test_shift_register.py`
3. GPIO pinlar raqamlarini tekshiring
4. Quvvat kuchlanishlarini tekshiring (5V va 12V)

### Tasodifiy signallar
1. Latch pin to'g'ri ulanganini tekshiring
2. Pull-down qarshiliklar qo'shing
3. Quvvat simlarini tekshiring

### ULN2803 issiq
1. Relay toki 500mA dan oshmaganini tekshiring
2. Sovutish radiatori qo'shing
3. Relay quvvat manbaini alohida qiling

## Kod o'zgarishlari

### GPIOController klassi
- `__init__` metodi: relay_map va shift_config qabul qiladi
- `shift_out` metodi: 8-bit ma'lumotni SN74HC595N ga yuboradi
- `set_pin` metodi: bitta relayni yoqadi/o'chiradi

### Relay holati
- Barcha relay holatlari bitta 8-bit `relay_state` o'zgaruvchida saqlanadi
- Har bir `set_pin` chaqiruvi butun holatni shift registerga yuboradi

## Texnik tafsilotlar

- **Data yuborish**: MSB first (7-bitdan 0-bitga)
- **Clock tezligi**: ~1kHz (Python bilan)
- **Maksimal relay**: 8 ta (bitta shift register bilan)
- **Kengaytirish**: Qo'shimcha shift registerlarni Q7' (pin 9) orqali zanjirlab ulash mumkin

## Mualliflik

Original loyiha: Moyka boshqaruv tizimi  
Shift register integratsiyasi: 2026

---

📖 Batafsil ma'lumot uchun `ULANISH.md` faylini o'qing  
🔧 Test uchun `test_shift_register.py` dan foydalaning  
💡 Savollar bo'lsa, documentation'ni o'qing
