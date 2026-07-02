import os

ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
_ENV_LOADED = False


def load_env():
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, _, val = line.partition("=")
                    os.environ[key.strip()] = val.strip()
    _ENV_LOADED = True
