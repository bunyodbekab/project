import json
import os

from app.settings import CONFIG_FILE, DEFAULT_CONFIG

SESSIONS_FILE = os.path.join(os.path.dirname(CONFIG_FILE), "sessions.json")


def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            for key, val in DEFAULT_CONFIG.items():
                if key not in data:
                    data[key] = val

            if "shift_register" not in data:
                data["shift_register"] = DEFAULT_CONFIG["shift_register"]

            for svc_name, svc_default in DEFAULT_CONFIG["services"].items():
                if svc_name not in data["services"]:
                    data["services"][svc_name] = dict(svc_default)
                    continue
                for k, v in svc_default.items():
                    if k not in data["services"][svc_name]:
                        data["services"][svc_name][k] = v
            
            # Remove "sessions" key if it exists (migration from old format)
            if "sessions" in data:
                del data["sessions"]
            
            return data
        except Exception:
            pass

    return json.loads(json.dumps(DEFAULT_CONFIG))


def save_config(cfg):
    try:
        # Ensure sessions are not saved in config
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
