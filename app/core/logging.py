"""
Configurazione del sistema di logging strutturato.
"""
import logging
import sys
from app.core.config import get_settings


def setup_logging() -> logging.Logger:
    """Configura e restituisce il logger principale dell'applicazione."""
    settings = get_settings()

    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    # Formatter leggibile in sviluppo, compatto in produzione
    if settings.is_production:
        fmt = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    else:
        fmt = "\033[36m%(asctime)s\033[0m | \033[1m%(levelname)-8s\033[0m | %(name)s | %(message)s"

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(fmt, datefmt="%Y-%m-%d %H:%M:%S"))

    root_logger = logging.getLogger("app")
    root_logger.setLevel(log_level)
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.propagate = False

    return root_logger


logger = setup_logging()
