import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def configure_logging(path: Path) -> logging.Logger:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("ai_daily")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not any(getattr(handler, "baseFilename", None) == str(path) for handler in logger.handlers):
        handler = RotatingFileHandler(path, maxBytes=1_000_000, backupCount=7, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
    return logger
