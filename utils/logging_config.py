import logging
import os
from typing import Optional

APP_LOG_LEVEL = os.getenv("APP_LOG_LEVEL", "INFO").upper()
APP_VERBOSE_LOGS = os.getenv("APP_VERBOSE_LOGS", "false").lower() == "true"


def _configure_root_logger():
    level = getattr(logging, APP_LOG_LEVEL, logging.INFO)
    root_logger = logging.getLogger()

    if not root_logger.handlers:
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        root_logger.addHandler(handler)

    root_logger.setLevel(level)

    # Rendre silencieux les librairies HTTP (toujours en WARNING même en mode verbeux)
    noisy_loggers = [
        "httpx",
        "httpcore",
        "httpcore.connection",
        "httpcore.http11",
        "httpcore.http2",
        "urllib3",
        "requests",
        "hpack",
        "botocore"
    ]
    for noisy in noisy_loggers:
        logging.getLogger(noisy).setLevel(logging.WARNING)


_configure_root_logger()


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """
    Retourne un logger configuré pour l'application.
    """
    return logging.getLogger(name or "narrando")


def verbose_logging_enabled() -> bool:
    """
    Indique si les logs verbeux (niveau DEBUG détaillé) sont activés.
    """
    return APP_VERBOSE_LOGS
