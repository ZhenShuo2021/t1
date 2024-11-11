import os
import random
import time
from abc import ABC, abstractmethod
from typing import Any

from ..common.config import Config, RuntimeConfig
from ..utils.security import AccountManager, Encryptor


class BaseBot(ABC):
    """Abstract base class for bots, defining shared behaviors."""

    def __init__(self, runtime_config: RuntimeConfig, base_config: Config):
        self.runtime_config = runtime_config
        self.config = base_config
        self.close_browser = runtime_config.terminate
        self.logger = runtime_config.logger

        self.encryptor = Encryptor(self.logger)
        self.account_manager = AccountManager(self.encryptor, self.logger)
        self.private_key, self.public_key = self.encryptor.load_keys()

        self.new_profile = False

    @abstractmethod
    def init_driver(self) -> Any:
        """Initialize the browser driver."""

    @abstractmethod
    def close_driver(self):
        """Close the browser and handle cleanup."""

    def prepare_chrome_profile(self):
        user_data_dir = self.config.chrome.profile_path

        if not os.path.exists(user_data_dir):
            os.makedirs(user_data_dir)
            self.new_profile = True
        else:
            self.new_profile = False

        return user_data_dir

    def auto_page_scroll(
        self, url: str, max_retry: int = 3, page_sleep: int = 5, fast_scroll: bool = True
    ) -> str:
        """Request handling with retries. To be implemented in subclasses."""
        raise NotImplementedError("Subclasses must implement automated retry logic.")

    def handle_login(self):
        """Login logic, implemented by subclasses."""
        raise NotImplementedError("Subclasses must implement login logic.")

    def human_like_type(self, element, text):
        """Simulate human-like typing into a field."""
        raise NotImplementedError("Subclasses must implement scroll behavior.")

    def scroll_page(self):
        """Simulate human-like scrolling behavior."""
        raise NotImplementedError("Subclasses must implement scroll behavior.")


class BaseBehavior:
    pause_time = (0.1, 0.3)

    @staticmethod
    def random_sleep(min_time=1.0, max_time=5.0):
        time.sleep(random.uniform(min_time, max_time))


class BaseScroll:
    def __init__(self, config, logger):
        self.config = config
        self.logger = logger
        self.scroll_position = 0
        self.last_content_height = 0
        self.successive_scroll_count = 0
        self.max_successive_scrolls = random.randint(5, 10)
