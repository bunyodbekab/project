import json
import os

from app.settings import CONFIG_FILE, DEFAULT_CONFIG


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
            return data
        except Exception:
            pass

    return json.loads(json.dumps(DEFAULT_CONFIG))


def save_config(cfg):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Config xatosi: {e}")
