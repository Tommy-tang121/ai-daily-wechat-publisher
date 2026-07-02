import json
import os

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "data", "config.json")
DEFAULT_CONFIG = {
    "title": "AI 行业热点新闻",
    "author": "Tommy",
    "max_words": 150,
    "schedule_time": "10:00",
    "data_source": "https://aihot.virxact.com/"
}

def _ensure_config():
    if not os.path.exists(CONFIG_PATH):
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, ensure_ascii=False, indent=2)
    return CONFIG_PATH

def get_config(key=None):
    _ensure_config()
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    if key:
        return cfg.get(key, DEFAULT_CONFIG.get(key))
    return cfg

def set_config(key, value):
    _ensure_config()
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    cfg[key] = value
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

def reset_config():
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(DEFAULT_CONFIG, f, ensure_ascii=False, indent=2)
