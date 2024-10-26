# src/automation/__init__.py
from .drission_bot import DrissionBot
from .get import get_bot
from .selenium_bot import SeleniumBot

# only import __all__ when using from automation import *
__all__ = ["SeleniumBot", "DrissionBot", "get_bot"]
