#!/usr/bin/env python3
"""
SN74HC595N Shift Register test dasturi
Har bir releni ketma-ket yoqib-o'chiradi
"""

import time
import gpiod

# GPIO pinlari (config.json dan)
DATA_PIN = 227   # SN74HC595N DS (14-pin)
CLOCK_PIN = 75   # SN74HC595N SHCP (11-pin)
LATCH_PIN = 79   # SN74HC595N STCP (12-pin)

CHIP_NAME = "gpiochip1"

class ShiftRegisterTest:
    def __init__(self):
        self.chip = gpiod.Chip(CHIP_NAME)
        
        # Pinlarni sozlash
        self.data_line = self.chip.get_line(DATA_PIN)
        self.data_line.request(consumer="test_data", type=gpiod.LINE_REQ_DIR_OUT, default_vals=[0])
        
        self.clock_line = self.chip.get_line(CLOCK_PIN)
        self.clock_line.request(consumer="test_clock", type=gpiod.LINE_REQ_DIR_OUT, default_vals=[0])
        
        self.latch_line = self.chip.get_line(LATCH_PIN)
        self.latch_line.request(consumer="test_latch", type=gpiod.LINE_REQ_DIR_OUT, default_vals=[0])
        
        print("Shift Register test tayyor")
        print(f"DATA: GPIO {DATA_PIN}")
        print(f"CLOCK: GPIO {CLOCK_PIN}")
        print(f"LATCH: GPIO {LATCH_PIN}")
        print()

    def shift_out(self, data_byte):
        """8-bitli ma'lumotni yuborish"""
        # Latch pastga
        self.latch_line.set_value(0)
        
        # 8 bitni yuborish (MSB first)
        for i in range(7, -1, -1):
            bit = (data_byte >> i) & 1
            
            # Clock pastga
            self.clock_line.set_value(0)
            
            # Data o'rnatish
            self.data_line.set_value(bit)
            
            # Clock yuqoriga (bit qabul qilinadi)
            self.clock_line.set_value(1)
        
        # Clock pastga
        self.clock_line.set_value(0)
        
        # Latch yuqoriga (chiqishga uzatish)
        self.latch_line.set_value(1)
        
        print(f"Yuborildi: {data_byte:08b} (decimal: {data_byte})")

    def test_all_on(self):
        """Barcha relelarni yoqish"""
        print("\n=== Barcha relelarni yoqish ===")
        self.shift_out(0xFF)  # 11111111
        time.sleep(2)

    def test_all_off(self):
        """Barcha relelarni o'chirish"""
        print("\n=== Barcha relelarni o'chirish ===")
        self.shift_out(0x00)  # 00000000
        time.sleep(1)

    def test_individual(self):
        """Har bir releni alohida test qilish"""
        print("\n=== Har bir releni ketma-ket test qilish ===")
        services = [
            (0, "KO'PIK"),
            (1, "SUV"),
            (2, "SHAMPUN"),
            (3, "VOSK"),
            (4, "PENA"),
            (5, "OSMOS"),
            (6, "QURITISH"),
            (7, "Zaxira"),
        ]
        
        for bit, name in services:
            value = 1 << bit  # Faqat bitta bitni yoqish
            print(f"\n{name} (bit {bit}):")
            self.shift_out(value)
            time.sleep(1.5)
        
        # Hammasini o'chirish
        print("\nHammasini o'chirish:")
        self.shift_out(0x00)

    def test_pattern(self):
        """Turli xil naqshlarni ko'rsatish"""
        print("\n=== Naqshlarni test qilish ===")
        
        patterns = [
            (0b10101010, "Toq bitlar"),
            (0b01010101, "Juft bitlar"),
            (0b11110000, "Yuqori 4 bit"),
            (0b00001111, "Quyi 4 bit"),
            (0b11001100, "2-2 bit"),
        ]
        
        for pattern, desc in patterns:
            print(f"\n{desc}: {pattern:08b}")
            self.shift_out(pattern)
            time.sleep(1.5)
        
        # O'chirish
        self.shift_out(0x00)

    def test_running_light(self):
        """Yuguruvchi chiroq effekti"""
        print("\n=== Yuguruvchi chiroq ===")
        
        for _ in range(3):  # 3 marta takrorlash
            for i in range(8):
                value = 1 << i
                self.shift_out(value)
                time.sleep(0.3)
        
        # O'chirish
        self.shift_out(0x00)

    def cleanup(self):
        """Tozalash va o'chirish"""
        self.shift_out(0x00)
        self.chip.close()
        print("\n\nTest yakunlandi. Chipset yopildi.")


def main():
    print("╔════════════════════════════════════════╗")
    print("║  SN74HC595N Shift Register Test       ║")
    print("║  Relay modullari uchun                 ║")
    print("╚════════════════════════════════════════╝")
    print()
    
    try:
        tester = ShiftRegisterTest()
        
        print("\nTestlar boshlanmoqda...")
        print("CTRL+C bosib to'xtatishingiz mumkin")
        print()
        time.sleep(2)
        
        # 1. Barcha relelarni yoqish
        tester.test_all_on()
        tester.test_all_off()
        
        # 2. Har bir releni alohida test
        tester.test_individual()
        time.sleep(1)
        
        # 3. Turli naqshlar
        tester.test_pattern()
        time.sleep(1)
        
        # 4. Yuguruvchi chiroq
        tester.test_running_light()
        
        print("\n✓ Barcha testlar muvaffaqiyatli yakunlandi!")
        
    except KeyboardInterrupt:
        print("\n\n⚠ Test to'xtatildi (CTRL+C)")
    except Exception as e:
        print(f"\n✗ Xatolik: {e}")
    finally:
        try:
            tester.cleanup()
        except:
            pass


if __name__ == "__main__":
    main()
