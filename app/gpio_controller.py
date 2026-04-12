import importlib

from app.settings import CHIP_NAME, DEBUG, INPUT_GPIO_TO_SERVICE, SHIFT_REGISTER_PINS
from app.storage import load_config

try:
    gpiod = importlib.import_module("gpiod")
except Exception:
    gpiod = None


class GPIOController:
    def __init__(self, relay_map):
        self.relay_map = relay_map  # {service_name: relay_bit}
        self.debug = DEBUG or gpiod is None

        shift_cfg = dict(SHIFT_REGISTER_PINS)
        try:
            cfg = load_config()
            runtime_shift_cfg = cfg.get("shift_register") if isinstance(cfg, dict) else None
            if isinstance(runtime_shift_cfg, dict):
                shift_cfg.update(runtime_shift_cfg)
        except Exception:
            pass

        self.data_pin = int(shift_cfg.get("data_pin", 227))
        self.clock_pin = int(shift_cfg.get("clock_pin", 75))
        self.latch_pin = int(shift_cfg.get("latch_pin", 79))

        self.chip = None
        self.out_bits = {}
        self.in_lines = {}
        self.out_states = {}
        self.out_request = None
        self.in_request = None
        self.relay_state = 0

        if self.debug:
            print("[DEBUG] Virtual GPIO rejimi yoqilgan. gpiod ishlatilmaydi.")
            self._print_virtual_state("Boshlang'ich holat")
            return

        for svc_name, relay_bit in self.relay_map.items():
            try:
                bit = int(relay_bit)
                if bit < 0 or bit > 7:
                    raise ValueError("relay_bit 0..7 oralig'ida bo'lishi kerak")
                self.out_bits[svc_name] = bit
            except Exception as e:
                print(f"Out BIT [svc={svc_name} bit={relay_bit}]: {e}")

        self.out_states = {svc_name: False for svc_name in self.out_bits}

        out_config = {
            self.data_pin: gpiod.LineSettings(
                direction=gpiod.line.Direction.OUTPUT,
                output_value=gpiod.line.Value.INACTIVE,
            ),
            self.clock_pin: gpiod.LineSettings(
                direction=gpiod.line.Direction.OUTPUT,
                output_value=gpiod.line.Value.INACTIVE,
            ),
            self.latch_pin: gpiod.LineSettings(
                direction=gpiod.line.Direction.OUTPUT,
                output_value=gpiod.line.Value.INACTIVE,
            ),
        }

        in_config = {}
        for gpio_line in INPUT_GPIO_TO_SERVICE:
            try:
                gpio_line = int(gpio_line)
                in_config[gpio_line] = gpiod.LineSettings(
                    direction=gpiod.line.Direction.INPUT,
                )
                self.in_lines[gpio_line] = gpio_line
            except Exception as e:
                print(f"In GPIO [line={gpio_line}]: {e}")

        try:
            if out_config:
                self.out_request = self._request_lines_with_fallback(
                    consumer="moyka_out",
                    config=out_config,
                )
            if in_config:
                self.in_request = self._request_lines_with_fallback(
                    consumer="moyka_in",
                    config=in_config,
                )
            self._shift_out(self.relay_state)
            print(f"GPIO tayyor (gpiod 2.x). Chip: {self.chip}")
        except Exception as e:
            print(f"GPIO chip xatosi: {e}")
            self.cleanup()

    def _chip_candidates(self):
        chip_name = str(CHIP_NAME)
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

    def _request_lines_with_fallback(self, consumer, config):
        candidates = self._chip_candidates()
        if self.chip in candidates:
            candidates = [self.chip] + [c for c in candidates if c != self.chip]

        errors = []
        for chip_candidate in candidates:
            try:
                request = gpiod.request_lines(
                    chip_candidate,
                    consumer=consumer,
                    config=config,
                )
                self.chip = chip_candidate
                return request
            except Exception as e:
                errors.append(f"{chip_candidate}: {e}")

        raise RuntimeError(" | ".join(errors))

    def _print_virtual_state(self, reason=""):
        if not self.debug:
            return
        ordered = sorted(self.relay_map.items(), key=lambda x: x[0])
        states = []
        for svc_name, relay_bit in ordered:
            on = 1 if getattr(self, "_virtual_state", {}).get(svc_name) else 0
            states.append(f"{svc_name}@bit{relay_bit}={'ON' if on else 'OFF'}")
        prefix = f"[DEBUG GPIO] {reason}: " if reason else "[DEBUG GPIO] "
        print(prefix + " | ".join(states))

    def _set_shift_pin(self, gpio_pin, high):
        if not self.out_request:
            return
        value = gpiod.line.Value.ACTIVE if high else gpiod.line.Value.INACTIVE
        self.out_request.set_value(gpio_pin, value)

    def _shift_out(self, data_byte):
        if self.debug or not self.out_request:
            return

        # Latch pastga
        self._set_shift_pin(self.latch_pin, False)

        # 8 bitni yuborish (MSB first)
        for i in range(7, -1, -1):
            bit = (data_byte >> i) & 1

            self._set_shift_pin(self.clock_pin, False)
            self._set_shift_pin(self.data_pin, bool(bit))
            self._set_shift_pin(self.clock_pin, True)

        self._set_shift_pin(self.clock_pin, False)
        self._set_shift_pin(self.latch_pin, True)

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

        relay_bit = self.out_bits.get(name)
        if relay_bit is None or not self.out_request:
            return

        try:
            new_value = bool(value)
            if self.out_states.get(name, False) == new_value:
                return

            if new_value:
                self.relay_state |= 1 << relay_bit
            else:
                self.relay_state &= ~(1 << relay_bit)

            self.out_states[name] = new_value
            self._shift_out(self.relay_state)
        except Exception as e:
            print(f"GPIO set xato [{name}]: {e}")

    def read_input(self, gpio_line):
        if self.debug:
            return 0
        if gpio_line in self.in_lines and self.in_request:
            try:
                value = self.in_request.get_value(gpio_line)
                return 1 if value == gpiod.line.Value.ACTIVE else 0
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

        if not self.out_request:
            return

        self.relay_state = 0
        for name in self.out_states:
            self.out_states[name] = False
        self._shift_out(self.relay_state)

    def cleanup(self):
        self.all_off()

        if self.in_request:
            try:
                self.in_request.release()
            except Exception:
                pass
            self.in_request = None

        if self.out_request:
            try:
                self.out_request.release()
            except Exception:
                pass
            self.out_request = None
