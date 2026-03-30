import importlib

from app.settings import CHIP_NAME, DEBUG, INPUT_GPIO_TO_SERVICE

try:
    gpiod = importlib.import_module("gpiod")
except Exception:
    gpiod = None


class GPIOController:
    def __init__(self, relay_map, shift_config):
        self.chip = None
        self.relay_map = relay_map
        self.relay_state = 0
        self.debug = DEBUG or gpiod is None

        self.data_line = None
        self.clock_line = None
        self.latch_line = None
        self.in_lines = {}

        if self.debug:
            print("[DEBUG] Virtual GPIO rejimi yoqilgan. gpiod ishlatilmaydi.")
            self._print_virtual_state("Boshlang'ich holat")
            return

        try:
            self.chip = gpiod.Chip(CHIP_NAME)

            data_pin = shift_config.get("data_pin", 227)
            clock_pin = shift_config.get("clock_pin", 75)
            latch_pin = shift_config.get("latch_pin", 79)

            try:
                self.data_line = self.chip.get_line(data_pin)
                self.data_line.request(consumer="sr_data", type=gpiod.LINE_REQ_DIR_OUT, default_vals=[0])

                self.clock_line = self.chip.get_line(clock_pin)
                self.clock_line.request(consumer="sr_clock", type=gpiod.LINE_REQ_DIR_OUT, default_vals=[0])

                self.latch_line = self.chip.get_line(latch_pin)
                self.latch_line.request(consumer="sr_latch", type=gpiod.LINE_REQ_DIR_OUT, default_vals=[0])

                print(f"Shift Register: DATA={data_pin}, CLOCK={clock_pin}, LATCH={latch_pin}")
            except Exception as e:
                print(f"Shift register GPIO xatosi: {e}")

            for gpio_line in INPUT_GPIO_TO_SERVICE:
                try:
                    line = self.chip.get_line(gpio_line)
                    line.request(consumer="moyka_in", type=gpiod.LINE_REQ_DIR_IN)
                    self.in_lines[gpio_line] = line
                except Exception as e:
                    print(f"In GPIO [line={gpio_line}]: {e}")

            self.shift_out(0)
            print("GPIO tayyor (Shift Register rejimida).")
        except Exception as e:
            print(f"GPIO chip xatosi: {e}")
            self.chip = None

    def _print_virtual_state(self, reason=""):
        if not self.debug:
            return
        ordered = sorted(self.relay_map.items(), key=lambda x: x[1])
        states = []
        for svc_name, bit_pos in ordered:
            on = 1 if (self.relay_state & (1 << bit_pos)) else 0
            states.append(f"{svc_name}={'ON' if on else 'OFF'}")
        prefix = f"[DEBUG GPIO] {reason}: " if reason else "[DEBUG GPIO] "
        print(prefix + f"byte={self.relay_state:08b} | " + " | ".join(states))

    def shift_out(self, data_byte):
        if not all([self.data_line, self.clock_line, self.latch_line]):
            print(f"[SIM] Shift out: {data_byte:08b}")
            return

        try:
            self.latch_line.set_value(0)
            for i in range(7, -1, -1):
                bit = (data_byte >> i) & 1
                self.clock_line.set_value(0)
                self.data_line.set_value(bit)
                self.clock_line.set_value(1)
            self.clock_line.set_value(0)
            self.latch_line.set_value(1)
        except Exception as e:
            print(f"Shift out xatosi: {e}")

    def set_pin(self, name, value):
        if name not in self.relay_map:
            print(f"[SIM] {name} -> {value}")
            return

        bit_pos = self.relay_map[name]

        if value:
            self.relay_state |= (1 << bit_pos)
            if self.debug:
                print(f"[DEBUG] {name} yoqildi")
        else:
            self.relay_state &= ~(1 << bit_pos)
            if self.debug:
                print(f"[DEBUG] {name} o'chirildi")

        self.shift_out(self.relay_state)
        self._print_virtual_state(name)

    def read_input(self, gpio_line):
        if self.debug:
            return 0
        if gpio_line in self.in_lines:
            try:
                return self.in_lines[gpio_line].get_value()
            except Exception:
                return 0
        return 0

    def all_off(self):
        self.relay_state = 0
        self.shift_out(0)
        self._print_virtual_state("Barchasi o'chdi")

    def cleanup(self):
        self.all_off()
        if self.chip:
            try:
                self.chip.close()
            except Exception:
                pass
