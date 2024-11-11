# v2dl/__init__.py
from .config import Config, ConfigManager, RuntimeConfig
from .error import DownloadError, FileProcessingError, ScrapeError
from .logger import setup_logging
from .scrapper import ScrapeHandler
from .utils.utils import ThreadingService
from .v2dl import ScrapeManager
from .web_bot import get_bot

__all__ = [
    "Config",
    "RuntimeConfig",
    "ConfigManager",
    "setup_logging",
    "ThreadingService",
    "ScrapeHandler",
    "ScrapeManager",
    "ScrapeError",
    "FileProcessingError",
    "DownloadError",
    "get_bot",
]

__version__ = "0.1.0"
