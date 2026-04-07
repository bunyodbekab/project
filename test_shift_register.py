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


def chip_candidates(chip_name):
    chip_name = str(chip_name)
    candidates = [chip_name]

    if chip_name.startswith("/dev/"):
        short_name = chip_name[5:]
        if short_name:
            candidates.append(short_name)
    else:
        candidates.append(f"/dev/{chip_name}")

    unique = []
    seen = set()
    for candidate in candidates:
        if candidate not in seen:
            seen.add(candidate)
            unique.append(candidate)
    return unique

class ShiftRegisterTest:
    def __init__(self):
        self.chip = None
        self.request = self._request_lines_with_fallback(
            consumer="shift-register-test",
            config={
                DATA_PIN: gpiod.LineSettings(
                    direction=gpiod.line.Direction.OUTPUT,
                    output_value=gpiod.line.Value.INACTIVE,
                ),
                CLOCK_PIN: gpiod.LineSettings(
                    direction=gpiod.line.Direction.OUTPUT,
                    output_value=gpiod.line.Value.INACTIVE,
                ),
                LATCH_PIN: gpiod.LineSettings(
                    direction=gpiod.line.Direction.OUTPUT,
                    output_value=gpiod.line.Value.INACTIVE,
                ),
            },
        )
        
        print("Shift Register test tayyor")
        print(f"DATA: GPIO {DATA_PIN}")
        print(f"CLOCK: GPIO {CLOCK_PIN}")
        print(f"LATCH: GPIO {LATCH_PIN}")
        print(f"CHIP: {self.chip}")
        print()

    def _request_lines_with_fallback(self, consumer, config):
        errors = []
        for chip_name in chip_candidates(CHIP_NAME):
            try:
                request = gpiod.request_lines(
                    chip_name,
                    consumer=consumer,
                    config=config,
                )
                self.chip = chip_name
                return request
            except Exception as e:
                errors.append(f"{chip_name}: {e}")
        raise RuntimeError(" | ".join(errors))

    def _set_pin(self, gpio_pin, high):
        value = gpiod.line.Value.ACTIVE if high else gpiod.line.Value.INACTIVE
        self.request.set_value(gpio_pin, value)

    def shift_out(self, data_byte):
        """8-bitli ma'lumotni yuborish"""
        # Latch pastga
        self._set_pin(LATCH_PIN, False)
        
        # 8 bitni yuborish (MSB first)
        for i in range(7, -1, -1):
            bit = (data_byte >> i) & 1
            
            # Clock pastga
            self._set_pin(CLOCK_PIN, False)
            
            # Data o'rnatish
            self._set_pin(DATA_PIN, bool(bit))
            
            # Clock yuqoriga (bit qabul qilinadi)
            self._set_pin(CLOCK_PIN, True)
        
        # Clock pastga
        self._set_pin(CLOCK_PIN, False)
        
        # Latch yuqoriga (chiqishga uzatish)
        self._set_pin(LATCH_PIN, True)
        
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
        self.request.release()
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
