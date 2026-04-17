"""Main Moyka UI widgets."""

import json
import math
import time
from datetime import datetime
from functools import partial

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFontMetrics
from PyQt6.QtWidgets import QApplication, QFrame, QGridLayout, QHBoxLayout, QLabel, QProgressBar, QSizePolicy, QVBoxLayout, QWidget

from app.game_logic import MathGameGenerator
from app.gpio_controller import GPIOController
from app.settings import BLINK_WARN, DEBUG, DEFAULT_CONFIG, INPUT_GPIO_TO_SERVICE, LOW_BALANCE, app_font
from app.storage import add_session, load_config, save_config
from .admin import AdminDialog, PinDialog
from .common import ClickableFrame, PauseButton, RotatedContainer, ServiceButton, _format_money


class MoykaUI(QWidget):
    def __init__(self, width, height):
        super().__init__()

        self.w = width
        self.h = height
        self.setFixedSize(width, height)
        self.setObjectName("MoykaRoot")

        self.cfg = load_config()
        relay_map = {
            name: data.get("relay_bit", data.get("gpio_out", idx % 8))
            for idx, (name, data) in enumerate(self.cfg["services"].items())
        }
        self.gpio = GPIOController(relay_map)

        self.front_settings = None
        self.front_services = []
        self.front_slots = {}
        self.front_key_to_hw = {}
        self.hw_to_front = {}
        self.price_per_sec = {}
        self.pause_free_default = 0
        self.pause_paid_rate = 1
        self.pause_free_left = 0
        self.pause_free_credit = 0
        self.pause_stage = "off"

        self.game_engine = MathGameGenerator()
        self.game_state = "idle"
        self.game_title = ""
        self.game_main_text = ""
        self.game_reward_total = 0
        self.game_correct_count = 0
        self.game_progress_max = 10.0
        self.game_progress_left = 0.0
        self.game_drain_rate = 1.0
        self.game_option_keys = []
        self.game_option_map = {}
        self.game_correct_answer = None
        self.game_question_text = ""
        self._game_ready_labels = [
            ("O'YIN", True),
            ("O'YIN-3", True),
            ("O'YIN-2", True),
            ("O'YIN-1", True),
            ("PAUZA", False),
        ]
        self._game_ready_index = 0
        self._game_ready_label = "PAUZA"
        self._game_ready_can_start = False
        self._game_cycle_consumed = False
        self._game_countdown_steps = []
        self._game_countdown_index = 0
        self._pending_game_start = False
        self._stop_long_triggered = False
        self._game_feedback_busy = False
        self._game_feedback_pending_action = ""

        self.balance = 0
        self.remaining_sec = 0
        self.active_service = None
        self.active_front_key = None
        self.is_running = False
        self.pause_mode = False
        self.show_timer_mode = False
        self.session_earned = 0
        self._bonus_awarded = False

        self.blink_state = False
        self._low_balance_flash = False
        self._button_press_lock_until = 0.0
        self._button_press_lock_sec = 0.5

        self._pause_hold_timer = QTimer(self)
        self._pause_hold_timer.setSingleShot(True)
        self._pause_hold_timer.setInterval(2000)
        self._pause_hold_timer.timeout.connect(self._pause_hold_tick)
        self._stop_hold_source = None
        self._stop_hold_started = None

        self._game_ready_timer = QTimer(self)
        self._game_ready_timer.setInterval(1000)
        self._game_ready_timer.timeout.connect(self._game_ready_tick)

        self._game_countdown_timer = QTimer(self)
        self._game_countdown_timer.setInterval(1000)
        self._game_countdown_timer.timeout.connect(self._game_countdown_tick)

        self._game_tick_timer = QTimer(self)
        self._game_tick_timer.setInterval(100)
        self._game_tick_timer.timeout.connect(self._game_tick)

        self._game_end_timer = QTimer(self)
        self._game_end_timer.setSingleShot(True)
        self._game_end_timer.timeout.connect(self._finish_game_cleanup)

        self._game_feedback_timer = QTimer(self)
        self._game_feedback_timer.setSingleShot(True)
        self._game_feedback_timer.timeout.connect(self._on_game_feedback_timeout)

        self.service_timer = QTimer(self)
        self.service_timer.setInterval(1000)
        self.service_timer.timeout.connect(self._tick)

        self.blink_timer = QTimer(self)
        self.blink_timer.setInterval(400)
        self.blink_timer.timeout.connect(self._blink)

        self.input_timer = QTimer(self)
        self.input_timer.setInterval(10)
        self.input_timer.timeout.connect(self._poll_inputs)
        self._prev_input = {line: 0 for line in INPUT_GPIO_TO_SERVICE}
        self._raw_input = {line: 0 for line in INPUT_GPIO_TO_SERVICE}
        self._raw_input_changed_at = {line: 0.0 for line in INPUT_GPIO_TO_SERVICE}
        self._service_debounce_ms = 70
        self._input_prime_left = 3
        self._inputs_primed = False
        self.input_timer.start()

        self._service_buttons = {}
        self._grid_dirty = True
        self._pin_dialog_open = False
        self._active_page_widget = None

        self._setup_ui()
        self._rebuild_front_services()
        self._emit_state()
        self._set_main_page_visible(True)

    def _setup_ui(self):
        # Match HTML/CSS clamp() calculations exactly
        # Header title: clamp(120px, 21.6vw, 180px)
        # Header main: clamp(120px, 11.2vw, 260px)
        title_responsive = int(self.w * 0.216)  # 21.6vw
        main_responsive = int(self.w * 0.112)   # 11.2vw
        
        self._title_px = max(120, min(180, title_responsive))
        self._main_px = max(120, min(260, main_responsive))
        
        # Top panel height: 34% of height (matching .top-panel flex: 0 0 34%)
        self._top_panel_height = max(260, int(self.h * 0.34))
        
        # Service button height: 12vh (reduced from 18.24vh)
        self._service_btn_height = int(self.h * 0.12)
        self._service_label_px = self._service_btn_height  # Will scale within button

        self.setStyleSheet(
            """
            QWidget#MoykaRoot {
                background: qlineargradient(y1:0, y2:1, stop:0 #081433, stop:1 #0a1436);
                color: #f8fafc;
            }
            QFrame#TopPanel {
                background: qlineargradient(y1:0, y2:1, stop:0 #081433, stop:1 #0a1436);
                border: 2px solid rgba(170, 206, 255, 145);
                border-radius: 24px;
            }
            QFrame#Divider {
                background: rgba(240, 248, 255, 230);
                border: none;
                max-height: 6px;
                border-radius: 3px;
            }
            QWidget#ControlsWrap {
                background: transparent;
                border: none;
            }
            QProgressBar#GameProgress {
                background: rgba(15, 23, 42, 0.65);
                border: 2px solid rgba(148, 163, 184, 0.45);
                border-radius: 12px;
                min-height: 24px;
                max-height: 24px;
                text-align: center;
                color: #e2e8f0;
                font-size: 15px;
                font-weight: 800;
            }
            QProgressBar#GameProgress::chunk {
                border-radius: 10px;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #22c55e, stop:1 #16a34a);
            }
            """
        )

        self._root_layout = QVBoxLayout(self)
        self._root_layout.setContentsMargins(0, 0, 0, 0)
        self._root_layout.setSpacing(0)

        self._main_page_shell = QWidget(self)
        self._main_page_shell.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        main_shell_layout = QHBoxLayout(self._main_page_shell)
        main_side_gap = max(12, int(self.w * 0.05))
        main_shell_layout.setContentsMargins(main_side_gap, 0, main_side_gap, 0)
        main_shell_layout.setSpacing(0)

        self._main_page_container = QWidget(self._main_page_shell)
        self._main_page_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        main_page_layout = QVBoxLayout(self._main_page_container)
        main_page_layout.setContentsMargins(0, 0, 0, 0)
        main_page_layout.setSpacing(0)
        main_shell_layout.addWidget(self._main_page_container, 1)

        self.top_panel = ClickableFrame(self._main_page_container)
        self.top_panel.setObjectName("TopPanel")
        self.top_panel.setFixedHeight(self._top_panel_height)
        self.top_panel.clicked.connect(self._on_top_panel_clicked)
        top_layout = QVBoxLayout(self.top_panel)
        # HTML: padding: 2.2vh 2vw 1.2vh
        top_padding_v = int(self.h * 0.022)
        top_padding_h = int(self.w * 0.02)
        top_layout.setContentsMargins(top_padding_h, top_padding_v, top_padding_h, int(self.h * 0.012))
        top_layout.setSpacing(int(self.h * 0.008))

        self.header_title = QLabel("XUSH KELIBSIZ")
        self.header_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.header_title.setWordWrap(True)
        self.header_title.setMinimumHeight(max(50, int(self._top_panel_height * 0.18)))
        self.header_title.setStyleSheet("font-weight: 800; letter-spacing: 0.01em; color: #d9deeb; padding: 4px 12px; min-width: 200px;")

        self.header_main = QLabel(self.cfg.get("moyka_name", "MOYKA"))
        self.header_main.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.header_main.setWordWrap(True)
        self.header_main.setMinimumHeight(max(72, int(self._top_panel_height * 0.24)))
        self.header_main.setStyleSheet("font-weight: 900; letter-spacing: 0.005em; color: #ffffff; padding: 4px 12px; min-width: 250px;")

        self.header_title.setFont(app_font(self._title_px, bold=True))
        self.header_main.setFont(app_font(self._main_px, bold=True))

        self.game_progress = QProgressBar(self.top_panel)
        self.game_progress.setObjectName("GameProgress")
        self.game_progress.setRange(0, 1000)
        self.game_progress.setValue(1000)
        self.game_progress.setTextVisible(False)
        self.game_progress.hide()
        

        top_layout.addStretch(1)
        top_layout.addWidget(self.header_title)
        top_layout.addWidget(self.header_main)
        top_layout.addWidget(self.game_progress)
        top_layout.addStretch(1)

        self.divider = QFrame(self._main_page_container)
        self.divider.setObjectName("Divider")

        self.controls_wrap = QWidget(self._main_page_container)
        self.controls_wrap.setObjectName("ControlsWrap")
        controls_layout = QVBoxLayout(self.controls_wrap)
        # HTML: padding: 2.2vh 2.6vw 2.5vh
        controls_padding_v_top = int(self.h * 0.012)
        controls_padding_h = 0
        controls_padding_v_bot = int(self.h * 0.025)
        controls_layout.setContentsMargins(controls_padding_h, controls_padding_v_top, controls_padding_h, controls_padding_v_bot)
        # HTML: gap: 1.45vh
        controls_layout.setSpacing(int(self.h * 0.0145))

        grid_holder = QWidget(self.controls_wrap)
        grid_holder.setObjectName("GridHolder")
        self.service_grid = QGridLayout(grid_holder)
        self.service_grid.setContentsMargins(0, 0, 0, int(self.w * 0.03))
        # HTML: gap: 3.35vh 2vw - increased for better spacing
        self.service_grid.setHorizontalSpacing(int(self.w * 0.03))
        self.service_grid.setVerticalSpacing(int(self.w * 0.03))
        self.service_grid.setColumnStretch(0, 1)
        self.service_grid.setColumnStretch(1, 1)  # Set to transparent to show parent background
        controls_layout.addWidget(grid_holder, 1)

        self.pause_button = PauseButton(self.controls_wrap)
        self.pause_button.pressedSignal.connect(lambda: self._on_stop_pressed("touch"))
        self.pause_button.releasedSignal.connect(lambda: self._on_stop_released("touch"))
        # Long-press PIN opening is handled by MoykaUI hold timer to avoid duplicate triggers.

        main_page_layout.addWidget(self.top_panel)
        main_page_layout.addWidget(self.divider)
        main_page_layout.addWidget(self.controls_wrap, 1)

        self._root_layout.addWidget(self._main_page_shell, 1)

    def _on_top_panel_clicked(self):
        if self.is_running or self.pause_mode or self._is_game_busy():
            return
        self.add_money(5000)

    def _deepcopy_default_config(self):
        return json.loads(json.dumps(DEFAULT_CONFIG))

    def reset_config_to_defaults(self):
        self.cfg = self._deepcopy_default_config()
        self.front_settings = None
        save_config(self.cfg)
        self._rebuild_front_services()
        self._emit_state()

    def _normalize_front_settings(self, raw):
        if not isinstance(raw, dict):
            return None

        services_raw = raw.get("services") or []
        if isinstance(services_raw, dict):
            services_raw = [{"name": name, **(svc or {})} for name, svc in services_raw.items()]
        if not isinstance(services_raw, list):
            services_raw = []

        norm_services = []
        seen = set()
        for idx, svc in enumerate(services_raw):
            if not isinstance(svc, dict):
                continue

            key_val = str(svc.get("name") or svc.get("key") or f"XIZMAT{idx + 1}")
            if key_val in seen:
                continue
            seen.add(key_val)

            cfg_svc = self.cfg.get("services", {}).get(key_val, {})
            price_per_sec = svc.get("price_per_sec") or svc.get("pricePerSec") or cfg_svc.get("price_per_sec", 0)
            sec_from_price = None
            try:
                if price_per_sec:
                    sec_from_price = math.ceil(5000 / max(1, int(price_per_sec)))
            except Exception:
                sec_from_price = None

            seconds = max(
                1,
                int(
                    svc.get("secondsPer5000")
                    or svc.get("seconds_per_5000")
                    or sec_from_price
                    or svc.get("duration")
                    or cfg_svc.get("duration", 60)
                ),
            )

            norm_services.append(
                {
                    "key": key_val,
                    "name": key_val,
                    "label": str(svc.get("label") or svc.get("display_name") or cfg_svc.get("display_name", key_val)),
                    "theme": str(svc.get("theme") or cfg_svc.get("theme") or "suv"),
                    "icon": str(svc.get("icon") or svc.get("icon_file") or cfg_svc.get("icon") or ""),
                    "showIcon": bool(svc.get("showIcon", True)),
                    "active": bool(svc.get("active", cfg_svc.get("active", True))),
                    "is_available": bool(
                        svc.get(
                            "is_available",
                            svc.get("isAvailable", cfg_svc.get("is_available", True)),
                        )
                    ),
                    "secondsPer5000": seconds,
                }
            )

        for key, cfg_svc in self.cfg.get("services", {}).items():
            if key in seen:
                continue
            seconds = max(1, math.ceil(5000 / max(1, int(cfg_svc.get("price_per_sec", 1)))))
            norm_services.append(
                {
                    "key": key,
                    "name": key,
                    "label": str(cfg_svc.get("display_name", key)),
                    "theme": str(cfg_svc.get("theme", "suv")),
                    "icon": str(cfg_svc.get("icon", "")),
                    "showIcon": True,
                    "active": bool(cfg_svc.get("active", True)),
                    "is_available": bool(cfg_svc.get("is_available", True)),
                    "secondsPer5000": seconds,
                }
            )

        pause_cfg = raw.get("pause") if isinstance(raw.get("pause"), dict) else {}
        free_value = pause_cfg.get("freeSeconds")
        if free_value is None:
            free_value = raw.get("freePause")
        if free_value is None:
            free_value = raw.get("free_pause")
        if free_value is None:
            free_value = (self.cfg.get("pause") or {}).get("freeSeconds", 0)

        paid_value = pause_cfg.get("paidSecondsPer5000")
        if paid_value is None:
            paid_value = raw.get("paidPause")
        if paid_value is None:
            paid_value = raw.get("paid_pause")
        if paid_value is None:
            paid_value = (self.cfg.get("pause") or {}).get("paidSecondsPer5000", 60)

        free_sec = max(0, int(free_value or 0))
        paid_sec = max(1, int(paid_value or 60))

        pin1 = str(raw.get("pin") or self.cfg.get("admin_pin", "1234"))

        bonus_percent = int(
            raw.get("bonusPercent")
            or raw.get("bonus_percent")
            or (raw.get("bonus") or {}).get("percent", 0)
            or self.cfg.get("bonus", {}).get("percent", 0)
        )
        bonus_threshold = int(
            raw.get("bonusThreshold")
            or raw.get("bonus_threshold")
            or (raw.get("bonus") or {}).get("threshold", 0)
            or self.cfg.get("bonus", {}).get("threshold", 0)
        )

        game_cfg_raw = raw.get("game") if isinstance(raw.get("game"), dict) else {}
        game_enabled = bool(
            raw.get("gameEnabled")
            if raw.get("gameEnabled") is not None
            else game_cfg_raw.get("enabled", (self.cfg.get("game") or {}).get("enabled", False))
        )
        game_min_balance = int(
            raw.get("gameMinBalance")
            or raw.get("game_min_balance")
            or game_cfg_raw.get("minBalance")
            or game_cfg_raw.get("min_balance")
            or (self.cfg.get("game") or {}).get("minBalance", 10000)
        )
        game_reward = int(
            raw.get("gameRewardPerCorrect")
            or raw.get("game_reward_per_correct")
            or game_cfg_raw.get("rewardPerCorrect")
            or game_cfg_raw.get("reward_per_correct")
            or (self.cfg.get("game") or {}).get("rewardPerCorrect", 500)
        )
        game_min_balance = max(0, game_min_balance)
        game_reward = max(1, game_reward)

        total_buttons = raw.get("totalButtons") or raw.get("buttonCount") or len(norm_services) or len(self.cfg.get("services", {})) or 1
        total_buttons = max(1, min(8, int(total_buttons)))

        show_icons = raw.get("showIcons")
        if show_icons is None:
            show_icons = raw.get("show_icons", self.cfg.get("show_icons", True))

        return {
            "pin": pin1,
            "totalButtons": int(total_buttons),
            "showIcons": bool(show_icons),
            "pause": {"freeSeconds": free_sec, "paidSecondsPer5000": paid_sec},
            "services": norm_services,
            "bonus": {"percent": bonus_percent, "threshold": bonus_threshold},
            "game": {
                "enabled": game_enabled,
                "minBalance": game_min_balance,
                "rewardPerCorrect": game_reward,
            },
        }

    def _apply_pause_settings(self):
        pause_cfg = None
        if self.front_settings:
            pause_cfg = self.front_settings.get("pause", {})
        if not pause_cfg:
            pause_cfg = self.cfg.get("pause") or {}

        self.pause_free_default = max(0, int((pause_cfg or {}).get("freeSeconds", 0)))
        paid_sec = max(1, int((pause_cfg or {}).get("paidSecondsPer5000", 60)))
        self.pause_paid_rate = max(1, math.ceil(5000 / paid_sec))

        # Free pause is a single credit per balance cycle.
        self.pause_free_credit = max(0, min(self.pause_free_credit, self.pause_free_default))
        if self.balance <= 0 and not self.is_running and not self.pause_mode:
            self.pause_free_credit = self.pause_free_default
            self.pause_free_left = self.pause_free_credit

    def _game_cfg(self):
        cfg = self.cfg.get("game") if isinstance(self.cfg.get("game"), dict) else {}
        return {
            "enabled": bool(cfg.get("enabled", False)),
            "minBalance": max(0, int(cfg.get("minBalance", cfg.get("min_balance", 10000)) or 0)),
            "rewardPerCorrect": max(1, int(cfg.get("rewardPerCorrect", cfg.get("reward_per_correct", 500)) or 500)),
        }

    def _is_game_busy(self):
        return self.game_state in ("countdown", "playing", "ended")

    def _is_game_playing(self):
        return self.game_state == "playing"

    def _can_offer_game(self):
        cfg = self._game_cfg()
        if not cfg.get("enabled"):
            return False
        if self._game_cycle_consumed:
            return False
        if self.is_running or self.pause_mode:
            return False
        if self._active_page_widget is not None or self._pin_dialog_open:
            return False
        if self._is_game_busy():
            return False
        return self.balance > cfg.get("minBalance", 0)

    def _game_option_front_keys(self):
        keys = []
        for slot in self.front_services:
            key = slot.get("front_key")
            if not key:
                continue
            keys.append(key)
        return keys

    def _map_to_hw_service(self, svc, used):
        requested = (svc.get("name") or svc.get("key") or "").strip()
        if requested and requested in self.cfg.get("services", {}) and requested not in used:
            used.add(requested)
            return requested

        for fallback in self.cfg.get("services", {}).keys():
            if fallback not in used:
                used.add(fallback)
                return fallback

        return None

    def _rebuild_front_services(self):
        services = []
        price_map = {}
        fk_to_hw = {}
        hw_to_fk = {}

        if self.front_settings:
            raw = self.front_settings.get("services", [])
            total = max(1, min(8, self.front_settings.get("totalButtons") or len(raw) or len(self.cfg.get("services", {})) or 1))
            used = set()
            for svc in raw:
                if not svc.get("active", True):
                    continue
                if len(services) >= total:
                    break
                hw_key = self._map_to_hw_service(svc, used)
                if not hw_key:
                    continue

                front_key = svc.get("key") or svc.get("name") or hw_key
                seconds = max(1, int(svc.get("secondsPer5000", 60)))
                price_map[front_key] = max(1, math.ceil(5000 / seconds))
                cfg_svc = self.cfg["services"].get(hw_key, {})

                services.append(
                    {
                        "front_key": front_key,
                        "label": svc.get("label") or cfg_svc.get("display_name", front_key),
                        "theme": svc.get("theme") or cfg_svc.get("theme", "suv"),
                        "icon_file": svc.get("icon") or cfg_svc.get("icon", ""),
                        "is_available": bool(
                            svc.get(
                                "is_available",
                                svc.get("isAvailable", cfg_svc.get("is_available", True)),
                            )
                        ),
                        "hw_key": hw_key,
                    }
                )
                fk_to_hw[front_key] = hw_key
                hw_to_fk[hw_key] = front_key
        else:
            for key, svc_cfg in self.cfg.get("services", {}).items():
                if not svc_cfg.get("active", True):
                    continue
                price_map[key] = max(1, int(svc_cfg.get("price_per_sec", 1)))
                services.append(
                    {
                        "front_key": key,
                        "label": svc_cfg.get("display_name", key),
                        "theme": svc_cfg.get("theme", "suv"),
                        "icon_file": svc_cfg.get("icon", ""),
                        "is_available": bool(svc_cfg.get("is_available", True)),
                        "hw_key": key,
                    }
                )
                fk_to_hw[key] = key
                hw_to_fk[key] = key

        self.front_services = services
        self.front_slots = {
            slot.get("front_key"): slot
            for slot in services
            if slot.get("front_key")
        }
        self.price_per_sec = price_map
        self.front_key_to_hw = fk_to_hw
        self.hw_to_front = hw_to_fk
        self.game_option_keys = self._game_option_front_keys()
        self._apply_pause_settings()
        self._grid_dirty = True

    def _set_service_labels_default(self):
        for key, btn in self._service_buttons.items():
            slot = self.front_slots.get(key, {})
            btn.set_game_mode(False)
            btn.restore_default_icon_mode()
            btn.set_label(slot.get("label", key), uppercase=True)
            btn.set_available(bool(slot.get("is_available", True)))

    def _set_game_option_labels(self, option_labels):
        option_labels = option_labels or {}
        for key, btn in self._service_buttons.items():
            btn.set_show_icon(False)
            btn.set_game_mode(True, "neutral")
            btn.set_available(True)
            btn.set_label(str(option_labels.get(key, "")), uppercase=False)

    def _update_game_ready_cycle(self):
        if self.balance <= 0 and not self._is_game_busy() and not self.is_running and not self.pause_mode:
            self._game_cycle_consumed = False
            self._game_ready_index = 0
            self._game_ready_label = "PAUZA"
            self._game_ready_can_start = False

        if self._game_ready_timer.isActive():
            if not self._can_offer_game():
                self._game_ready_timer.stop()
                self._game_ready_label = "PAUZA"
                self._game_ready_can_start = False
            return

        if self._can_offer_game() and self._game_ready_index == 0:
            self._game_ready_timer.start()
            self._game_ready_tick()
            return

        self._game_ready_label = "PAUZA"
        self._game_ready_can_start = False

    def _game_ready_tick(self):
        if not self._can_offer_game():
            self._update_game_ready_cycle()
            return

        if self._game_ready_index >= len(self._game_ready_labels):
            self._game_ready_timer.stop()
            self._game_ready_label = "PAUZA"
            self._game_ready_can_start = False
            self._game_ready_index = 0
            self._game_cycle_consumed = True
            self._emit_state()
            return

        label, can_start = self._game_ready_labels[self._game_ready_index]
        self._game_ready_label = str(label)
        self._game_ready_can_start = bool(can_start)
        self._game_ready_index += 1
        self._emit_state()

    def _sync_game_progress_bar(self):
        if self.game_state != "playing":
            self.game_progress.hide()
            return

        self.game_progress.show()
        max_val = max(0.1, float(self.game_progress_max))
        ratio = max(0.0, min(1.0, float(self.game_progress_left) / max_val))
        self.game_progress.setValue(int(ratio * 1000))

    def _start_game(self):
        if not self._can_offer_game() or not self._game_ready_can_start:
            return

        option_keys = self._game_option_front_keys()
        if len(option_keys) < 2:
            self.game_state = "ended"
            self.game_title = "O'YIN"
            self.game_main_text = "KAMIDA 2 TA TUGMA KERAK"
            self.game_reward_total = 0
            self._emit_state()
            self._game_end_timer.start(1800)
            return

        self._pending_game_start = False
        self._pause_hold_timer.stop()
        self._game_ready_timer.stop()
        self._game_ready_can_start = False
        self._game_ready_label = "PAUZA"
        self._game_ready_index = 0
        self._game_cycle_consumed = True
        self._stop_hold_source = None
        self._stop_hold_started = None
        self._game_feedback_timer.stop()
        self._game_feedback_busy = False
        self._game_feedback_pending_action = ""

        self.service_timer.stop()
        self.blink_timer.stop()
        self.blink_state = False

        self.game_state = "countdown"
        self.game_title = "O'YIN"
        self.game_main_text = "3"
        self.game_reward_total = 0
        self.game_correct_count = 0
        self.game_progress_max = 10.0
        self.game_progress_left = self.game_progress_max
        self.game_drain_rate = 1.0
        self.game_option_keys = option_keys
        self.game_option_map = {}
        self.game_correct_answer = None
        self.game_question_text = ""

        self._game_countdown_steps = [
            ("O'YIN", "3"),
            ("O'YIN", "2"),
            ("O'YIN", "1"),
            ("O'YIN BOSHLANDI", ""),
        ]
        self._game_countdown_index = 0
        self._set_game_option_labels({key: "-" for key in self.game_option_keys})

        self._game_countdown_tick()
        self._game_countdown_timer.start()

    def _game_countdown_tick(self):
        if self.game_state != "countdown":
            self._game_countdown_timer.stop()
            return

        if self._game_countdown_index < len(self._game_countdown_steps):
            title, main_text = self._game_countdown_steps[self._game_countdown_index]
            self.game_title = str(title)
            self.game_main_text = str(main_text)
            self._game_countdown_index += 1
            self._emit_state()
            return

        self._game_countdown_timer.stop()
        self._start_game_play()

    def _start_game_play(self):
        if self.game_state != "countdown":
            return

        self.game_state = "playing"
        self.game_progress_max = 8.0
        self.game_progress_left = self.game_progress_max
        self.game_drain_rate = 1.0

        self._next_game_round()
        self._game_tick_timer.start()
        self._emit_state()

    def _next_game_round(self):
        if self.game_state != "playing":
            return

        option_count = max(2, len(self.game_option_keys))
        round_data = self.game_engine.build_round(option_count=option_count, streak=self.game_correct_count)

        option_labels = {}
        option_values = {}
        for idx, key in enumerate(self.game_option_keys):
            value = int(round_data.options[idx])
            option_labels[key] = str(value)
            option_values[key] = value

        self.game_question_text = round_data.expression
        self.game_correct_answer = int(round_data.correct_answer)
        self.game_option_map = option_values
        self.game_title = f"BALANS: +{_format_money(self.game_reward_total)} SO'M"
        self.game_main_text = self.game_question_text
        self._set_game_option_labels(option_labels)

    def _front_key_for_correct_answer(self):
        for key, value in self.game_option_map.items():
            if int(value) == int(self.game_correct_answer):
                return key
        return None

    def _set_game_feedback(self, selected_key, correct_key, is_correct):
        for key, btn in self._service_buttons.items():
            if key == correct_key:
                status = "correct"
            else:
                status = "wrong"
            btn.set_game_mode(True, status)

    def _on_game_feedback_timeout(self):
        self._game_feedback_busy = False
        action = self._game_feedback_pending_action
        self._game_feedback_pending_action = ""

        if action == "next" and self.game_state == "playing":
            self._next_game_round()
            self._emit_state()
            return

        if action == "end":
            self._end_game()

    def _handle_game_answer(self, front_key):
        if self.game_state != "playing":
            return

        if self._game_feedback_busy:
            return

        answer = self.game_option_map.get(front_key)
        if answer is None:
            return

        correct_key = self._front_key_for_correct_answer()

        if int(answer) != int(self.game_correct_answer):
            self._set_game_feedback(front_key, correct_key, is_correct=False)
            self._game_feedback_busy = True
            self._game_feedback_pending_action = "end"
            self._game_feedback_timer.start(700)
            self._emit_state()
            return

        reward = self._game_cfg().get("rewardPerCorrect", 500)
        self.balance += reward
        self.game_reward_total += reward
        self.game_correct_count += 1

        self.game_progress_left = min(self.game_progress_max + 2.5, self.game_progress_left + 1.7)
        self.game_drain_rate = min(4.8, 1.0 + (self.game_correct_count * 0.18))

        self._set_game_feedback(front_key, correct_key, is_correct=True)
        self._game_feedback_busy = True
        self._game_feedback_pending_action = "next"
        self._game_feedback_timer.start(450)
        self._emit_state()

    def _game_tick(self):
        if self.game_state != "playing":
            self._game_tick_timer.stop()
            return

        self.game_progress_left = max(0.0, self.game_progress_left - (0.1 * self.game_drain_rate))
        if self.game_progress_left <= 0.0:
            self._end_game()
            return

        self._sync_game_progress_bar()

    def _end_game(self):
        if self.game_state not in ("countdown", "playing"):
            return

        self._game_feedback_timer.stop()
        self._game_feedback_busy = False
        self._game_feedback_pending_action = ""
        self._game_countdown_timer.stop()
        self._game_tick_timer.stop()

        self.game_state = "ended"
        self.game_title = "O'YIN TUGADI"
        self.game_main_text = f"+{_format_money(self.game_reward_total)} SO'M"
        self.game_option_map = {}
        self.game_correct_answer = None

        self._emit_state()
        self._game_end_timer.start(2200)

    def _finish_game_cleanup(self):
        self._game_countdown_timer.stop()
        self._game_tick_timer.stop()
        self._game_end_timer.stop()
        self._game_feedback_timer.stop()

        self.game_state = "idle"
        self.game_title = ""
        self.game_main_text = ""
        self.game_reward_total = 0
        self.game_correct_count = 0
        self.game_progress_left = 0.0
        self.game_option_map = {}
        self.game_correct_answer = None
        self.game_question_text = ""
        self._pending_game_start = False
        self._stop_long_triggered = False
        self._game_feedback_busy = False
        self._game_feedback_pending_action = ""
        self._set_service_labels_default()
        self._emit_state()

    def update_front_settings(self, settings):
        norm = self._normalize_front_settings(settings)
        if not norm:
            return

        self.front_settings = norm
        single_pin = str(norm.get("pin", self.cfg.get("admin_pin", "1234")))
        self.cfg["admin_pin"] = single_pin
        self.cfg["admin_pin_alt"] = single_pin
        self.cfg["show_icons"] = bool(norm.get("showIcons", self.cfg.get("show_icons", True)))

        bonus_cfg = norm.get("bonus", {}) or {}
        self.cfg["bonus"] = {
            "percent": int(bonus_cfg.get("percent", 0) or 0),
            "threshold": int(bonus_cfg.get("threshold", 0) or 0),
        }

        pause_cfg = norm.get("pause", {}) or {}
        self.cfg["pause"] = {
            "freeSeconds": int(pause_cfg.get("freeSeconds", 0) or 0),
            "paidSecondsPer5000": int(pause_cfg.get("paidSecondsPer5000", 60) or 60),
        }

        game_cfg = norm.get("game", {}) or {}
        self.cfg["game"] = {
            "enabled": bool(game_cfg.get("enabled", False)),
            "minBalance": int(game_cfg.get("minBalance", 10000) or 0),
            "rewardPerCorrect": int(game_cfg.get("rewardPerCorrect", 500) or 500),
        }

        for svc in norm.get("services", []):
            key = svc.get("name") or svc.get("key")
            if not key or key not in self.cfg["services"]:
                continue

            seconds = max(1, int(svc.get("secondsPer5000", 60)))
            price_per_sec = max(1, math.ceil(5000 / seconds))
            display_name = svc.get("label") or svc.get("display_name") or self.cfg["services"][key].get("display_name", key)

            target = self.cfg["services"][key]
            target["price_per_sec"] = price_per_sec
            target["duration"] = max(1, int(svc.get("duration", seconds)))
            target["display_name"] = display_name
            if "icon" in svc:
                target["icon"] = str(svc.get("icon") or target.get("icon", ""))
            if "theme" in svc:
                target["theme"] = str(svc.get("theme") or target.get("theme", "suv"))
            target["active"] = bool(svc.get("active", target.get("active", True)))
            target["is_available"] = bool(
                svc.get(
                    "is_available",
                    svc.get("isAvailable", target.get("is_available", True)),
                )
            )

        save_config(self.cfg)
        self._rebuild_front_services()
        self._emit_state()

    def _display_title_for_service(self, service_key):
        for slot in self.front_services:
            if slot.get("hw_key") == service_key or slot.get("front_key") == service_key:
                return str(slot.get("label", "")).replace("\n", " ")
        return self.cfg["services"].get(service_key, {}).get("display_name", service_key).upper()

    def _header_color(self, mode, pause_status="off"):
        if self._low_balance_flash:
            return "#ff4d4d"
        if self.blink_timer.isActive() and self.blink_state:
            return "#ff4d4d"
        if mode == "game":
            return "#dcfce7"
        if mode == "pause":
            return "#ffd84d" if pause_status == "free" else "#ff4d4d"
        return "#ffffff"

    def _state_dict(self):
        mode = "idle"
        title = ""
        main_text = ""

        pause_state = {
            "status": "off",
            "remainingText": "",
            "label": "",
        }

        if self._is_game_busy():
            mode = "game"
            title = self.game_title
            main_text = self.game_main_text
        elif self.pause_mode:
            mode = "pause"
            remaining = max(0, self.remaining_sec)
            pause_state["status"] = "free" if self.pause_stage == "free" else "paid"
            pause_state["label"] = "TEKIN PAUZA" if self.pause_stage == "free" else "PAUZA"
            pause_state["remainingText"] = "{:02d}:{:02d}".format(remaining // 60, remaining % 60)
            title = pause_state["label"]
            main_text = pause_state["remainingText"]
        elif self.show_timer_mode and self.is_running and self.active_service:
            mode = "running"
            title = self._display_title_for_service(self.active_service)
            main_text = "{:02d}:{:02d}".format(max(0, self.remaining_sec) // 60, max(0, self.remaining_sec) % 60)
        else:
            balance_value = max(0, self.balance)
            if balance_value <= 0:
                title = "XUSH KELIBSIZ"
                main_text = self.cfg.get("moyka_name", "MOYKA")
            else:
                title = "BALANS"
                main_text = f"{_format_money(balance_value)}\nSO'M"

        services = []
        for slot in self.front_services:
            if not slot.get("front_key"):
                continue
            services.append(
                {
                    "key": slot["front_key"],
                    "name": slot["front_key"],
                    "label": slot["label"],
                    "theme": slot["theme"],
                    "icon": slot.get("icon_file", ""),
                    "is_available": bool(slot.get("is_available", True)),
                }
            )

        return {
            "mode": mode,
            "title": title,
            "mainText": main_text,
            "headerColor": self._header_color(mode, pause_state.get("status", "off")),
            "balanceText": _format_money(self.balance),
            "activeService": self.active_front_key or "",
            "services": services,
            "pauseState": pause_state,
            "canAddMoney": mode == "idle",
            "total_earned": self.cfg.get("total_earned", 0),
            "admin_pins": [self.cfg.get("admin_pin", "1234")],
            "bonus": self.cfg.get("bonus", {}),
            "game": self.cfg.get("game", {}),
            "debug": bool(DEBUG),
        }

    def _settings_payload(self):
        return {
            "pin": self.cfg.get("admin_pin", "1234"),
            "showIcons": bool(self.cfg.get("show_icons", True)),
            "show_icons": bool(self.cfg.get("show_icons", True)),
            "bonus": self.cfg.get("bonus", {}),
            "game": self.cfg.get("game", {}),
            "pause": self.cfg.get("pause", {}),
            "totalButtons": len(self.cfg.get("services", {})),
            "services": [
                {
                    "name": key,
                    "key": key,
                    "label": svc.get("display_name", key),
                    "display_name": svc.get("display_name", key),
                    "price_per_sec": svc.get("price_per_sec", 1),
                    "secondsPer5000": max(1, math.ceil(5000 / max(1, svc.get("price_per_sec", 1)))),
                    "duration": svc.get("duration", 60),
                    "relay_bit": svc.get("relay_bit"),
                    "icon": svc.get("icon", ""),
                    "theme": svc.get("theme", "suv"),
                    "active": bool(svc.get("active", True)),
                    "is_available": bool(svc.get("is_available", True)),
                    "isAvailable": bool(svc.get("is_available", True)),
                }
                for key, svc in self.cfg.get("services", {}).items()
            ],
            "moyka_name": self.cfg.get("moyka_name", "MOYKA"),
        }

    def _refresh_service_grid(self):
        while self.service_grid.count():
            item = self.service_grid.takeAt(0)
            widget = item.widget()
            if widget is not None and widget is not self.pause_button:
                widget.deleteLater()

        self._service_buttons = {}
        show_icons = bool(self.cfg.get("show_icons", True))
        
        # Match HTML/CSS: .service-btn height: 12vh (reduced)
        btn_height = int(self.h * 0.12)
        
        # Match HTML/CSS: .service-label clamp(40.8px, 5.88vh, 79.2px)
        label_responsive = int(self.h * 0.0588)
        # Keep button labels closer in size across short/long names.
        btn_font_px_raw = max(34, min(62, label_responsive))
        btn_font_px = max(18, int(btn_font_px_raw / 1.5))

        for idx, slot in enumerate(self.front_services):
            front_key = slot.get("front_key")
            if not front_key:
                continue

            btn = ServiceButton(
                label=slot.get("label", front_key),
                theme=slot.get("theme", "suv"),
                icon_file=slot.get("icon_file", ""),
                show_icon=show_icons,
            )
            btn.setMinimumHeight(btn_height)
            btn.setMaximumHeight(btn_height)
            btn.set_font_px(btn_font_px)
            btn.set_available(bool(slot.get("is_available", True)))
            btn.clicked.connect(partial(self.button_clicked, front_key))

            row = idx // 2
            col = idx % 2
            self.service_grid.addWidget(btn, row, col)
            self._service_buttons[front_key] = btn

        count = len(self.front_services)
        # Match HTML/CSS: .pause-button height: 12vh (reduced to match service buttons)
        pause_height = btn_height
        pause_text_responsive = int(self.h * 0.048)
        pause_main_px_raw = max(35, min(70, pause_text_responsive))
        pause_main_px = max(22, int(pause_main_px_raw / 1.2))
        pause_sub_px = max(12, int((pause_main_px_raw * 0.5) / 1.2))
        # Use the same icon sizing formula as ServiceButton for consistency
        pause_mark_px = max(70, min(90, int(btn_font_px * 0.95)))
        
        self.pause_button.setMinimumHeight(pause_height)
        self.pause_button.setMaximumHeight(pause_height)
        self.pause_button.set_font_px(pause_main_px, pause_sub_px, pause_mark_px)
        
        pause_row = count // 2
        if count % 2 == 1:
            self.service_grid.addWidget(self.pause_button, pause_row, 1)
        else:
            self.service_grid.addWidget(self.pause_button, pause_row, 0, 1, 2)

        if self.game_state == "playing":
            self._set_game_option_labels({k: str(v) for k, v in self.game_option_map.items()})
        elif self.game_state == "countdown":
            self._set_game_option_labels({key: "-" for key in self.game_option_keys})
        elif self.game_state == "ended":
            self._set_game_option_labels({})
        else:
            self._set_service_labels_default()

        if self._main_page_shell.isVisible():
            self._apply_user_cursor_visibility(True)

        self._grid_dirty = False

    def _render_state(self):
        if self._grid_dirty:
            self._refresh_service_grid()

        state = self._state_dict()
        mode = state.get("mode", "idle")
        title = state.get("title", "")
        main_text = state.get("mainText", "")
        header_color = state.get("headerColor", "#ffffff")
        is_balance_mode = mode == "idle" and title == "BALANS"

        self.header_title.setText(title)
        if is_balance_mode:
            money_text = _format_money(max(0, self.balance))
            self.header_main.setTextFormat(Qt.TextFormat.RichText)
            self.header_main.setText(
                f"<div style='line-height:0.86;'>{money_text}<br><span style='font-size:0.34em;'>SO'M</span></div>"
            )
        else:
            self.header_main.setTextFormat(Qt.TextFormat.PlainText)
            self.header_main.setText(main_text)
        self.header_title.setStyleSheet(
            f"font-weight: 800; letter-spacing: 0.6px; color: {header_color};"
        )
        self.header_main.setStyleSheet(
            f"font-weight: 800; letter-spacing: 0.6px; color: {header_color};"
        )

        title_scale = 1.0
        main_scale = 1.0
        if mode in ("running", "pause"):
            title_scale = 1.2
            main_scale = 1.3
        elif mode == "game":
            title_scale = 1.12
            main_scale = 1.05

        if is_balance_mode:
            title_scale = 0.56
            main_scale = 0.80

        if mode == "running":
            main_scale *= 1.1

        self.header_title.setFont(app_font(max(20, int(self._title_px * title_scale)), bold=True))
        self.header_main.setFont(app_font(max(30, int(self._main_px * main_scale)), bold=True))
        if is_balance_mode:
            max_width = max(180, int(max(1, self.top_panel.width()) * 0.86))
            self._fit_label_font(
                self.header_title,
                self.header_title.text(),
                max(14, int(self._title_px * title_scale)),
                14,
                max_width,
            )
        else:
            self._fit_header_fonts(title_scale=title_scale, main_scale=main_scale)

        active_front_key = state.get("activeService")
        for key, btn in self._service_buttons.items():
            btn.set_active(bool(self.is_running and key == active_front_key))

        pause_state = state.get("pauseState", {}) or {}
        is_pause = mode == "pause"
        is_free = pause_state.get("status") == "free"
        pause_label = pause_state.get("label") or ("TEKIN PAUZA" if is_free else "PAUZA")
        if mode == "game":
            self.pause_button.set_state(False, False, "O'YIN", "", mode="game")
        elif is_pause:
            # Keep pause timer internal; do not show countdown inside the pause button.
            self.pause_button.set_state(True, is_free, pause_label, "", mode="pause")
        elif self._can_offer_game():
            ready_label = self._game_ready_label
            if str(ready_label).startswith("O'YIN"):
                self.pause_button.set_state(False, False, ready_label, "", mode="game")
            else:
                self.pause_button.set_state(False, False, "PAUZA", "", mode="pause")
        else:
            self.pause_button.set_state(False, False, "PAUZA", "", mode="pause")

        self._sync_game_progress_bar()

    def _fit_label_font(self, label, text, target_px, min_px, max_width):
        text = str(text or "")
        lines = [line for line in text.splitlines() if line] or [text]
        px = max(min_px, int(target_px))
        while px > min_px:
            font = app_font(px, bold=True)
            fm = QFontMetrics(font)
            widest_line = max(fm.horizontalAdvance(line) for line in lines)
            if widest_line <= max_width:
                break
            px -= 1
        label.setFont(app_font(px, bold=True))

    def _fit_header_fonts(self, title_scale=1.0, main_scale=1.0):
        if not hasattr(self, "top_panel"):
            return
        panel_w = max(1, self.top_panel.width())
        panel_h = max(1, self.top_panel.height())
        size_ref = max(1, min(panel_w, panel_h))

        # Use the smaller panel side as a stable base so idle/balance states stay consistent.
        max_width = max(180, int(panel_w * 0.86))
        title_target = max(20, int(self._title_px * max(1.0, float(title_scale))))
        main_target = max(30, int(self._main_px * max(1.0, float(main_scale))))
        title_cap = max(26, int(size_ref * 0.13 * max(1.0, float(title_scale))))
        main_cap = max(42, int(size_ref * 0.19 * max(1.0, float(main_scale))))
        title_px = min(title_target, title_cap)
        main_px = min(main_target, main_cap)
        self._fit_label_font(self.header_title, self.header_title.text(), title_px, 20, max_width)
        self._fit_label_font(self.header_main, self.header_main.text(), main_px, 30, max_width)

    def _emit_state(self):
        self._update_game_ready_cycle()
        self._render_state()

    def add_money(self, amount=5000):
        self.balance += amount
        self._apply_bonus_if_needed()
        self._emit_state()
        self._check_blink()

    def _apply_bonus_if_needed(self):
        bonus_cfg = self.cfg.get("bonus", {}) or {}
        pct = max(0, int(bonus_cfg.get("percent", 0)))
        threshold = max(0, int(bonus_cfg.get("threshold", 0)))
        if pct <= 0 or threshold <= 0:
            return
        if self._bonus_awarded:
            return
        if self.balance >= threshold:
            extra = int((self.balance * pct) / 100)
            if extra > 0:
                self.balance += extra
                self._bonus_awarded = True

    def _buttons_locked(self):
        return time.monotonic() < self._button_press_lock_until

    def _lock_buttons(self, seconds=None):
        lock_sec = self._button_press_lock_sec if seconds is None else max(0.0, float(seconds))
        self._button_press_lock_until = max(self._button_press_lock_until, time.monotonic() + lock_sec)

    def _front_slot(self, front_key):
        return self.front_slots.get(front_key)

    def button_clicked(self, front_key):
        if self._is_game_playing():
            if self._game_feedback_busy:
                return
            if self._buttons_locked():
                return
            self._lock_buttons(0.12)
            self._handle_game_answer(front_key)
            return

        if self.game_state in ("countdown", "ended"):
            return

        if self._buttons_locked():
            return

        front_key = front_key or ""
        slot = self._front_slot(front_key)
        if not slot:
            return
        if not bool(slot.get("is_available", True)):
            return

        self._lock_buttons()

        hw_key = slot.get("hw_key") or self.front_key_to_hw.get(front_key, front_key)
        price = self.price_per_sec.get(front_key)
        print(f"[CLICK] front_key={front_key} hw_key={hw_key} price={price} balance={self.balance}")
        if hw_key not in self.cfg["services"]:
            print(f"[CLICK] hw_key {hw_key} not in services")
            return

        cost = max(1, int(price or self.cfg["services"][hw_key].get("price_per_sec", 1)))

        if self.balance < cost:
            self._flash_low_balance()
            return

        if self.pause_mode:
            self._stop_pause()

        if self.is_running and self.active_service:
            self._deactivate_pin(self.active_service)

        self._pause_hold_timer.stop()
        self._stop_hold_source = None

        self.active_service = hw_key
        self.active_front_key = front_key
        self.pause_mode = False
        self.pause_stage = "off"
        # Charge one extra second on every accepted service button press
        # so rapid switching cannot bypass time deduction.
        press_charge = min(cost, self.balance)
        self.balance -= press_charge
        self.session_earned += press_charge
        if self.balance <= 0:
            self._stop_service(manual_pause=False)
            return

        self.remaining_sec = math.ceil(self.balance / cost)
        self.is_running = True
        self.show_timer_mode = True
        self.session_earned = 0
        self.session_earned += press_charge

        self._activate_pin(hw_key)
        self.service_timer.start()
        self._emit_state()
        self._check_blink()

    def _on_stop_pressed(self, source="touch"):
        if self._is_game_busy():
            return

        if self._buttons_locked():
            return
        self._lock_buttons(0.15)

        self._stop_long_triggered = False
        self._pending_game_start = False

        if self._can_offer_game() and self._game_ready_can_start and not self.is_running and not self.pause_mode:
            if source == "gpio":
                self._start_game()
                return
            self._pending_game_start = True

        self._stop_hold_source = source
        self._stop_hold_started = time.monotonic()
        if source == "touch":
            self._pause_hold_timer.start()
        else:
            self._pause_hold_timer.stop()
        if self.is_running:
            self._stop_service(manual_pause=True)

    def _on_stop_released(self, source="touch"):
        self._pause_hold_timer.stop()

        if self._pending_game_start and not self._stop_long_triggered:
            self._pending_game_start = False
            self._start_game()

        self._stop_hold_started = None
        self._stop_hold_source = None

    def _pause_hold_tick(self):
        self._pause_hold_timer.stop()
        self._stop_long_triggered = True
        self._pending_game_start = False
        # Open PIN only after a real long-press timeout from touch input.
        if self._stop_hold_source == "touch" and not self.is_running and not self._is_game_busy():
            self._open_pin_modal()
        self._stop_hold_source = None
        self._stop_hold_started = None

    def _open_pin_modal(self):
        if self._pin_dialog_open:
            return

        self._pin_dialog_open = True
        self._set_main_page_visible(False)
        self._clear_active_page_widget()

        pins = [self.cfg.get("admin_pin", "1234")]
        dialog = PinDialog(pins, self, on_clear_money=self._clear_money_and_time)
        dialog.setModal(False)
        dialog.setWindowFlags(Qt.WindowType.Widget)
        dialog.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        dialog.accepted.connect(self._on_pin_page_accepted)
        dialog.rejected.connect(self._on_pin_page_rejected)

        page_container = self._wrap_page_container(dialog)
        self._active_page_widget = page_container
        self._root_layout.addWidget(page_container, 1)

    def _open_admin_panel(self):
        self._clear_active_page_widget()

        dialog = AdminDialog(self, self)
        dialog.setModal(False)
        dialog.setWindowFlags(Qt.WindowType.Widget)
        dialog.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        dialog.accepted.connect(self._on_admin_page_closed)
        dialog.rejected.connect(self._on_admin_page_closed)

        page_container = self._wrap_page_container(dialog)
        self._active_page_widget = page_container
        self._root_layout.addWidget(page_container, 1)

    def _return_to_main(self):
        self._clear_active_page_widget()
        self._set_main_page_visible(True)
        self._pin_dialog_open = False
        self._emit_state()

    def _set_main_page_visible(self, visible):
        visible = bool(visible)
        self._main_page_shell.setVisible(visible)
        self._apply_user_cursor_visibility(visible)

    def _apply_user_cursor_visibility(self, hide_cursor):
        cursor = Qt.CursorShape.BlankCursor if hide_cursor else Qt.CursorShape.ArrowCursor
        self.setCursor(cursor)
        self._main_page_shell.setCursor(cursor)
        self.top_panel.setCursor(cursor)
        self.pause_button.setCursor(cursor)
        for btn in self._service_buttons.values():
            btn.setCursor(cursor)

    def _wrap_page_container(self, page_widget):
        container = QWidget(self)
        container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        side_gap = max(12, int(self.w * 0.05))
        layout = QHBoxLayout(container)
        layout.setContentsMargins(side_gap, 0, side_gap, 0)
        layout.setSpacing(0)
        layout.addWidget(page_widget, 1)
        return container

    def _clear_active_page_widget(self):
        if self._active_page_widget is None:
            return
        self._root_layout.removeWidget(self._active_page_widget)
        self._active_page_widget.setParent(None)
        self._active_page_widget.deleteLater()
        self._active_page_widget = None

    def _on_pin_page_accepted(self):
        self._open_admin_panel()

    def _on_pin_page_rejected(self):
        self._return_to_main()

    def _on_admin_page_closed(self):
        self._return_to_main()

    def _on_pause_button_long_pressed(self):
        """Triggered when pause button is held for 2 seconds."""
        self._open_pin_modal()

    def _clear_money_and_time(self):
        if self._is_game_busy():
            self._finish_game_cleanup()
        if self.pause_mode:
            self._stop_pause()
        elif self.is_running:
            self._stop_service(manual_pause=False)

        self.balance = 0
        self.remaining_sec = 0
        self.show_timer_mode = False
        self.pause_mode = False
        self.pause_stage = "off"
        self.pause_free_credit = self.pause_free_default
        self.pause_free_left = self.pause_free_credit
        self._bonus_awarded = False
        self._emit_state()
        self._check_blink()

    def _tick(self):
        if self._is_game_busy():
            return

        if self.pause_mode:
            self._tick_pause()
            return

        if not self.is_running or not self.active_service:
            return

        cost = max(
            1,
            int(self.price_per_sec.get(self.active_front_key) or self.cfg["services"][self.active_service].get("price_per_sec", 1)),
        )

        if self.balance <= 0:
            self._stop_service()
            return

        charge = min(cost, self.balance)
        self.balance -= charge
        self.session_earned += charge
        self.remaining_sec = math.ceil(self.balance / cost) if self.balance > 0 else 0

        if self.balance <= 0:
            self._stop_service()
            return

        self._emit_state()
        self._check_blink()

    def _tick_pause(self):
        if not self.pause_mode:
            return

        if self.pause_stage == "free" and self.pause_free_left > 0:
            self.pause_free_left = max(0, self.pause_free_left - 1)
            self.pause_free_credit = self.pause_free_left
            self.remaining_sec = self.pause_free_left
            if self.pause_free_left <= 0:
                self.pause_stage = "paid"
                self.pause_free_credit = 0
                self.remaining_sec = math.ceil(self.balance / self.pause_paid_rate) if self.balance > 0 else 0
            self._emit_state()
            return

        cost = max(1, int(self.pause_paid_rate))
        if self.balance <= 0:
            self._stop_pause()
            return

        charge = min(cost, self.balance)
        self.balance -= charge
        self.session_earned += charge
        self.remaining_sec = math.ceil(self.balance / cost) if self.balance > 0 else 0

        if self.balance <= 0:
            self._stop_pause()
            return

        self._emit_state()
        self._check_blink()

    def _stop_pause(self):
        self.pause_mode = False
        self.pause_stage = "off"
        self.pause_free_left = self.pause_free_credit
        self.service_timer.stop()

        if self.session_earned > 0:
            self.cfg["total_earned"] = self.cfg.get("total_earned", 0) + self.session_earned
            add_session(
                {
                    "service": "PAUSE",
                    "service_name": "PAUZA",
                    "earned": self.session_earned,
                    "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
            )
            save_config(self.cfg)

        self.session_earned = 0
        self._bonus_awarded = False

        # New cycle starts only after full balance depletion.
        if self.balance <= 0:
            self.pause_free_credit = self.pause_free_default
            self.pause_free_left = self.pause_free_credit

        self._emit_state()
        self._check_blink()

    def _stop_service(self, manual_pause=False):
        self.is_running = False
        self.show_timer_mode = manual_pause
        self.pause_mode = manual_pause and self.balance > 0
        self.service_timer.stop()
        self.blink_timer.stop()
        self.blink_state = False

        if self.active_service and self.session_earned > 0:
            service_display = self.cfg["services"].get(self.active_service, {}).get("display_name", self.active_service)
            self.cfg["total_earned"] = self.cfg.get("total_earned", 0) + self.session_earned
            add_session(
                {
                    "service": self.active_service,
                    "service_name": service_display,
                    "earned": self.session_earned,
                    "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
            )
            save_config(self.cfg)

        if self.active_service:
            self._deactivate_pin(self.active_service)
            self.active_service = None
            self.active_front_key = None

        if self.balance <= 0:
            self._bonus_awarded = False
            self.pause_free_credit = self.pause_free_default

        if self.pause_mode:
            self.pause_stage = "free" if self.pause_free_credit > 0 else "paid"
            self.pause_free_left = self.pause_free_credit
            if self.pause_stage == "free":
                self.remaining_sec = self.pause_free_left
            else:
                self.remaining_sec = math.ceil(self.balance / self.pause_paid_rate) if self.balance > 0 else 0
            self.session_earned = 0
            self.service_timer.start()
        else:
            self.session_earned = 0
            self.pause_stage = "off"
            self.pause_free_left = self.pause_free_credit
            self.pause_mode = False

        self._emit_state()
        self._check_blink()

    def _check_blink(self):
        should = (self.is_running or self.pause_mode) and (self.remaining_sec <= 3)
        if should and not self.blink_timer.isActive():
            self.blink_timer.start()
            self._emit_state()
        elif not should and self.blink_timer.isActive():
            self.blink_timer.stop()
            self.blink_state = False
            self._emit_state()

    def _blink(self):
        self.blink_state = not self.blink_state
        self._emit_state()

    def _flash_low_balance(self):
        self._low_balance_flash = True
        self._emit_state()

        def reset_flash():
            self._low_balance_flash = False
            self._emit_state()

        QTimer.singleShot(700, reset_flash)

    def _poll_inputs(self):
        # Keep relay outputs latched according to current state every poll cycle.
        self.gpio.refresh_relay_outputs()

        if not self._inputs_primed:
            now = time.monotonic()
            for gpio_line in INPUT_GPIO_TO_SERVICE:
                val = self.gpio.read_input(gpio_line)
                self._prev_input[gpio_line] = val
                self._raw_input[gpio_line] = val
                self._raw_input_changed_at[gpio_line] = now

            self._input_prime_left = max(0, self._input_prime_left - 1)
            if self._input_prime_left <= 0:
                self._inputs_primed = True
            return

        now = time.monotonic()
        for gpio_line, svc_name in INPUT_GPIO_TO_SERVICE.items():
            raw_val = self.gpio.read_input(gpio_line)
            if raw_val != self._raw_input.get(gpio_line, raw_val):
                self._raw_input[gpio_line] = raw_val
                self._raw_input_changed_at[gpio_line] = now

            prev = self._prev_input.get(gpio_line, 0)
            val = raw_val

            if str(svc_name).startswith("XIZMAT"):
                last_change = self._raw_input_changed_at.get(gpio_line, now)
                if (now - last_change) * 1000.0 < self._service_debounce_ms:
                    val = prev
                else:
                    val = self._raw_input.get(gpio_line, raw_val)

            if svc_name == "STOP":
                if val == 1 and prev == 0:
                    self.pause_button.pulse_click()
                    self._on_stop_pressed("gpio")
                elif val == 0 and prev == 1:
                    self._on_stop_released("gpio")
            elif svc_name == "PUL":
                if val == 1 and prev == 0:
                    self.add_money(1000)
            elif val == 1 and prev == 0:
                front_key = self.hw_to_front.get(svc_name, svc_name)
                btn = self._service_buttons.get(front_key)
                if btn and btn.isEnabled():
                    btn.pulse_click()
                self.button_clicked(front_key)

            self._prev_input[gpio_line] = val

    def _activate_pin(self, name):
        if not name:
            return
        self.gpio.all_off()
        self.gpio.set_pin(name, 1)

    def _deactivate_pin(self, name):
        if not name:
            return
        self.gpio.set_pin(name, 0)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Enter, Qt.Key.Key_Return):
            self._on_top_panel_clicked()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event):
        self._game_ready_timer.stop()
        self._game_countdown_timer.stop()
        self._game_tick_timer.stop()
        self._game_end_timer.stop()
        self._game_feedback_timer.stop()
        self.gpio.cleanup()
        super().closeEvent(event)

    def resizeEvent(self, event):
        self._emit_state()
        super().resizeEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        # First render can happen before final geometry; schedule one more pass.
        QTimer.singleShot(0, self._emit_state)


class RotatedWindow(QWidget):
    def __init__(self):
        super().__init__()
        sg = QApplication.primaryScreen().geometry()
        sw = sg.width()
        sh = sg.height()

        self.setStyleSheet("background: qlineargradient(y1:0, y2:1, stop:0 #081433, stop:1 #0a1436);")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Render UI in swapped dimensions and rotate by -90 degrees.
        self.ui = MoykaUI(sh, sw)
        self.rotated = RotatedContainer(self.ui, -90, self, fallback_size=(sw, sh))
        layout.addWidget(self.rotated)

    def show_ui(self):
        self.showFullScreen()

    def keyPressEvent(self, event):
        self.ui.keyPressEvent(event)
        if event.key() == Qt.Key.Key_Escape:
            QApplication.quit()
