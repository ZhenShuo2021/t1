# v2dl/__init__.py
from .config import Config, ConfigManager
from .custom_logger import setup_logging
from .v2dl import DownloadError, FileProcessingError, ScrapeError, ScrapeManager
from .web_bot import get_bot

__all__ = [
    "Config",
    "ConfigManager",
    "setup_logging",
    "ScrapeManager",
    "ScrapeError",
    "FileProcessingError",
    "DownloadError",
    "get_bot",
]

__version__ = "0.1.0"
