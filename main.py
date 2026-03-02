import gpiod
import time

CHIP_NAME = "gpiochip1"

# Hozircha ehtimoliy pinlar (xavfsizlar)
CANDIDATE_LINES = [
    6,
    7,
    12,
    75,
    227,
]

chip = gpiod.Chip(CHIP_NAME)

print("=== Relay scan boshlandi ===")

for line_num in CANDIDATE_LINES:
    try:
        line = chip.get_line(line_num)

        # output sifatida olish
        line.request(
            consumer="relay-scan",
            type=gpiod.LINE_REQ_DIR_OUT,
            default_vals=[0],
        )

        print(f"Testing line {line_num} ...")

        # YOQISH
        line.set_value(1)
        time.sleep(1)

        # O‘CHIRISH
        line.set_value(0)
        line.release()

        print("-----------------------")

    except Exception as e:
        print(f"Line {line_num} ishlamadi: {e}")

print("=== Scan tugadi ===")