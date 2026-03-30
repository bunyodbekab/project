Orange Pi 3 Zero (GPIO) uchun qo'shimcha ma'lumot
=================================================

Ushbu loyiha Orange Pi 3 Zero da sinovdan o'tgan. Quyida input pinlar va
ularni tanlash bo'yicha amaliy tavsiyalar keltirilgan.

1) Loyiha uchun ishlatilayotgan pinlar
-------------------------------------
Output (shift register uchun):
- GPIO 227  -> SN74HC595N DS (data)
- GPIO 75   -> SN74HC595N SHCP (clock)
- GPIO 79   -> SN74HC595N STCP (latch)

Input (tugmalar):
- GPIO 229  -> KO'PIK
- GPIO 228  -> SUV
- GPIO 73   -> SHAMPUN
- GPIO 70   -> VOSK
- GPIO 72   -> PENA
- GPIO 231  -> OSMOS
- GPIO 232  -> QURITISH
- GPIO 230  -> STOP

Bu pin mapping kodda INPUT_GPIO_TO_SERVICE lug'atida belgilangan.

2) Qaysi pinlardan input sifatida foydalansa bo'ladi
----------------------------------------------------
- 40-pin headerdagi oddiy GPIO pinlaridan foydalaning.
- Shift register uchun band qilingan GPIO 227/75/79 ni inputga bermang.
- Har doim 3.3V logika darajasini saqlang (5V bilan bevosita ulash mumkin emas).
- Agar pinlar boshqa periferiya (UART, SPI, I2C) bilan ishlatilmasa, ularni input
  sifatida ishlatish qulay.

3) Input pinlar turi va ulash tavsiyalari
-----------------------------------------
Tugma ulanayotganda ikki xil usuldan biri ishlatiladi:

A) Pull-up bilan (tavsiya):
- GPIO -> tugma -> GND
- Tashqi 10k rezistor bilan pull-up (yoki ichki pull-up, agar OS va gpiod
  konfiguratsiya qilinsa)
- Tugma bosilganda signal 0 bo'ladi.

B) Pull-down bilan:
- GPIO -> tugma -> 3.3V
- Tashqi 10k pull-down rezistor
- Tugma bosilganda signal 1 bo'ladi.

Amalda pull-up usuli shovqinga chidamli bo'ladi. Agar ichki pull-up/pull-down
ishlatilmasa, tashqi rezistor qo'yish tavsiya etiladi.

4) Qaysi pinlardan qaysi maqsadda foydalanish yaxshiroq
--------------------------------------------------------
- Shift register boshqaruvi (data/clock/latch) uchun bir xil portdagi pinlarni
  tanlash barqaror ishlashga yordam beradi (signal vaqti yaqin bo'ladi).
- Input tugmalar uchun alohida, bo'sh GPIO pinlar tanlang.
- Bir xil joylashgan (bir header qatorida yaqin) pinlar montajni yengillashtiradi.
- 5V va 3.3V quvvat pinlarini hech qachon GPIO sifatida ishlatmang.
- GND pinlardan birini tugmalar uchun umumiy yer sifatida ishlatish qulay.

5) Pinlarni aniqlash va tekshirish
----------------------------------
A) gpioinfo (tavsiya):
- sudo gpioinfo
  Shu yerda gpiochip1 bo'limidan kerakli line raqamlarini tekshiring.

B) gpio readall (agar mavjud bo'lsa):
- sudo gpio readall

C) Line raqamini hisoblash formulasi:
- GPIO Line = (Port * 32) + Pin
  Masalan: PC7 = (2 * 32) + 7 = 71

6) Kodda pinlarni o'zgartirish
-------------------------------
Input mapping:
- main.py ichidagi INPUT_GPIO_TO_SERVICE lug'ati

Shift register pinlari:
- config.json ichidagi shift_register (data_pin, clock_pin, latch_pin)

7) Xavfsizlik va barqarorlik tavsiyalari
----------------------------------------
- Har doim 3.3V logika darajasini saqlang.
- Tugmalarga debounce (dasturiy) qo'shish foydali bo'lishi mumkin.
- Ulanishlarni quvvat o'chirilgan holatda bajaring.

Qo'shimcha ma'lumot uchun:
- GPIO_TOPISH.md
- ULANISH.md
- README_SHIFT.md
