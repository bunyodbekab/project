import json
import os

from app.settings import CONFIG_FILE, DEFAULT_CONFIG

SESSIONS_FILE = os.path.join(os.path.dirname(CONFIG_FILE), "sessions.json")


def _deepcopy_default():
    """Return a deep copy of DEFAULT_CONFIG without mutating the source."""
    return json.loads(json.dumps(DEFAULT_CONFIG))


def _migrate_service_fields(data):
    # Legacy names -> yangi XIZMAT nomlari
    legacy_order = ["KO'PIK", "SUV", "SHAMPUN", "VOSK", "PENA", "OSMOS", "QURITISH"]
    new_order = ["XIZMAT1", "XIZMAT2", "XIZMAT3", "XIZMAT4", "XIZMAT5", "XIZMAT6", "XIZMAT7"]
    if any(key in data.get("services", {}) for key in legacy_order) and all(k not in data.get("services", {}) for k in new_order):
        migrated = {}
        for legacy, new in zip(legacy_order, new_order):
            if legacy in data["services"]:
                migrated[new] = data["services"].get(legacy, {})
        data["services"] = migrated

    # migrate output mapping to relay_bit and fill new UI fields
    for svc_name, svc_default in DEFAULT_CONFIG["services"].items():
        if svc_name not in data["services"]:
            data["services"][svc_name] = dict(svc_default)
            continue
        svc_cfg = data["services"][svc_name]
        if "relay_bit" not in svc_cfg:
            gpio_out = svc_cfg.get("gpio_out")
            if isinstance(gpio_out, int) and 0 <= gpio_out <= 7:
                svc_cfg["relay_bit"] = gpio_out
            else:
                svc_cfg["relay_bit"] = svc_default.get("relay_bit", 0)
        for k, v in svc_default.items():
            if k not in svc_cfg:
                svc_cfg[k] = v

        # Keep legacy key out of runtime config so UI/controller use relay_bit consistently.
        svc_cfg.pop("gpio_out", None)


def load_config():
    data = None
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = None

    if data is None:
        return _deepcopy_default()

    # fill missing top-level keys
    for key, val in DEFAULT_CONFIG.items():
        if key not in data:
            data[key] = val

    if "services" not in data or not isinstance(data["services"], dict):
        data["services"] = _deepcopy_default()["services"]

    _migrate_service_fields(data)

    # Ensure bonus structure exists
    if "bonus" not in data:
        data["bonus"] = {"percent": 0, "threshold": 0}
    else:
        data["bonus"].setdefault("percent", 0)
        data["bonus"].setdefault("threshold", 0)

    if "pause" not in data:
        data["pause"] = {"freeSeconds": 5, "paidSecondsPer5000": 120}
    else:
        data["pause"].setdefault("freeSeconds", 5)
        data["pause"].setdefault("paidSecondsPer5000", 120)

    if "game" not in data:
        data["game"] = {"enabled": False, "minBalance": 10000, "rewardPerCorrect": 500}
    else:
        if "minBalance" not in data["game"] and "min_balance" in data["game"]:
            data["game"]["minBalance"] = data["game"].get("min_balance")
        if "rewardPerCorrect" not in data["game"] and "reward_per_correct" in data["game"]:
            data["game"]["rewardPerCorrect"] = data["game"].get("reward_per_correct")
        data["game"].setdefault("enabled", False)
        data["game"].setdefault("minBalance", 10000)
        data["game"].setdefault("rewardPerCorrect", 500)

    if "show_icons" not in data:
        data["show_icons"] = True

    # drop legacy keys
    data.pop("sessions", None)

    return data


def save_config(cfg):
    try:
        cfg_copy = dict(cfg)
        cfg_copy.pop("sessions", None)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg_copy, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Config xatosi: {e}")


def load_sessions():
    """Load session history from sessions.json"""
    if os.path.exists(SESSIONS_FILE):
        try:
            with open(SESSIONS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []


def save_sessions(sessions):
    """Save session history to sessions.json"""
    try:
        with open(SESSIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(sessions, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Sessiyalarni saqlashda xato: {e}")


def add_session(session_data):
    """Add a new session to the sessions file"""
    try:
        sessions = load_sessions()
        sessions.append(session_data)
        save_sessions(sessions)
    except Exception as e:
        print(f"Sessiya qo'shishda xato: {e}")
