import importlib

from app.settings import CHIP_NAME, DEBUG, INPUT_GPIO_TO_SERVICE

try:
    gpiod = importlib.import_module("gpiod")
except Exception:
    gpiod = None


class GPIOController:
    def __init__(self, relay_map):
        self.relay_map = relay_map  # {service_name: gpio_out}
        self.debug = DEBUG or gpiod is None
        self.master_enable_gpio = 226

        self.chip = None
        self.out_lines = {}
        self.in_lines = {}
        self.out_states = {}
        self.out_request = None
        self.in_request = None

        if self.debug:
            print("[DEBUG] Virtual GPIO rejimi yoqilgan. gpiod ishlatilmaydi.")
            self._print_virtual_state("Boshlang'ich holat")
            return

        out_config = {}
        for svc_name, gpio_out in self.relay_map.items():
            try:
                gpio_line = int(gpio_out)
                out_config[gpio_line] = gpiod.LineSettings(
                    direction=gpiod.line.Direction.OUTPUT,
                    output_value=gpiod.line.Value.INACTIVE,
                )
                self.out_lines[svc_name] = gpio_line
            except Exception as e:
                print(f"Out GPIO [svc={svc_name} line={gpio_out}]: {e}")

        out_config[self.master_enable_gpio] = gpiod.LineSettings(
            direction=gpiod.line.Direction.OUTPUT,
            output_value=gpiod.line.Value.INACTIVE,
        )
        self.out_states = {svc_name: False for svc_name in self.out_lines}

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
        for svc_name, gpio_out in ordered:
            on = 1 if getattr(self, "_virtual_state", {}).get(svc_name) else 0
            states.append(f"{svc_name}@{gpio_out}={'ON' if on else 'OFF'}")
        prefix = f"[DEBUG GPIO] {reason}: " if reason else "[DEBUG GPIO] "
        print(prefix + " | ".join(states))

    def _any_output_active(self):
        return any(self.out_states.get(name, False) for name in self.out_lines)

    def _set_master_enable(self, active):
        if self.debug:
            return
        if not self.out_request:
            return
        try:
            value = gpiod.line.Value.ACTIVE if active else gpiod.line.Value.INACTIVE
            self.out_request.set_value(self.master_enable_gpio, value)
        except Exception as e:
            print(f"GPIO set xato [master={self.master_enable_gpio}]: {e}")

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

        gpio_line = self.out_lines.get(name)
        if gpio_line is None or not self.out_request:
            return

        # Har bir yoqish/o'chirishda avval master GPIO ni yoqib olamiz.
        self._set_master_enable(True)
        try:
            gpio_value = gpiod.line.Value.ACTIVE if value else gpiod.line.Value.INACTIVE
            self.out_request.set_value(gpio_line, gpio_value)
            self.out_states[name] = bool(value)
        except Exception as e:
            print(f"GPIO set xato [{name}]: {e}")
        finally:
            self._set_master_enable(self._any_output_active())

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

        self._set_master_enable(True)
        for name, gpio_line in self.out_lines.items():
            try:
                self.out_request.set_value(gpio_line, gpiod.line.Value.INACTIVE)
                self.out_states[name] = False
            except Exception as e:
                print(f"GPIO off xato [{name}]: {e}")

        self._set_master_enable(False)

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
