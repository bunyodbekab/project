import importlib

from app.settings import CHIP_NAME, DEBUG, INPUT_GPIO_TO_SERVICE

try:
    gpiod = importlib.import_module("gpiod")
except Exception:
    gpiod = None


class GPIOController:
    def __init__(self, relay_map):
        self.chip = None
        self.relay_map = relay_map  # {service_name: gpio_out}
        self.debug = DEBUG or gpiod is None

        self.out_lines = {}
        self.in_lines = {}

        if self.debug:
            print("[DEBUG] Virtual GPIO rejimi yoqilgan. gpiod ishlatilmaydi.")
            self._print_virtual_state("Boshlang'ich holat")
            return

        try:
            self.chip = gpiod.Chip(CHIP_NAME)

            # prepare outputs
            for svc_name, gpio_out in self.relay_map.items():
                try:
                    line = self.chip.get_line(int(gpio_out))
                    line.request(consumer=f"{svc_name}_out", type=gpiod.LINE_REQ_DIR_OUT, default_vals=[0])
                    self.out_lines[svc_name] = line
                except Exception as e:
                    print(f"Out GPIO [svc={svc_name} line={gpio_out}]: {e}")

            # prepare inputs
            for gpio_line in INPUT_GPIO_TO_SERVICE:
                try:
                    line = self.chip.get_line(gpio_line)
                    line.request(consumer="moyka_in", type=gpiod.LINE_REQ_DIR_IN)
                    self.in_lines[gpio_line] = line
                except Exception as e:
                    print(f"In GPIO [line={gpio_line}]: {e}")

            print("GPIO tayyor (to'g'ridan-to'g'ri chiqish).")
        except Exception as e:
            print(f"GPIO chip xatosi: {e}")
            self.chip = None

    def _print_virtual_state(self, reason=""):
        if not self.debug:
            return
        ordered = sorted(self.relay_map.items(), key=lambda x: x[0])
        states = []
        for svc_name, gpio_out in ordered:
            on = 1 if getattr(self, "_virtual_state", {}).get(svc_name) else 0
            states.append(f"{svc_name}@{gpio_out}={'ON' if on else 'OFF'}")
        prefix = f"[DEBUG GPIO] {reason}: " if reason else "[DEBUG GPIO] "
        print(prefix + " | ".join(states))

    def set_pin(self, name, value):
        if name not in self.relay_map:
            print(f"[SIM] {name} -> {value}")
            return

        if self.debug:
            if not hasattr(self, "_virtual_state"):
                self._virtual_state = {}
            self._virtual_state[name] = bool(value)
            self._print_virtual_state(name)
            return

        line = self.out_lines.get(name)
        if not line:
            return
        try:
            line.set_value(1 if value else 0)
        except Exception as e:
            print(f"GPIO set xato [{name}]: {e}")

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
        if self.debug:
            if not hasattr(self, "_virtual_state"):
                self._virtual_state = {}
            for k in self.relay_map:
                self._virtual_state[k] = False
            self._print_virtual_state("Barchasi o'chdi")
            return

        for name, line in self.out_lines.items():
            try:
                line.set_value(0)
            except Exception as e:
                print(f"GPIO off xato [{name}]: {e}")

    def cleanup(self):
        self.all_off()
        if self.chip:
            try:
                self.chip.close()
            except Exception:
                pass
