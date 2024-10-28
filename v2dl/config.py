import argparse
import logging
import os
import platform
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv


@dataclass
class RuntimeConfig:
    url: str
    bot_type: str
    terminate: bool
    download_service: Any
    dry_run: bool
    logger: Any
    log_level: int
    no_skip: bool = False


@dataclass
class DownloadConfig:
    min_scroll_length: int
    max_scroll_length: int
    min_scroll_step: int
    max_scroll_step: int
    rate_limit: int
    download_dir: str


@dataclass
class PathConfig:
    download_log: str
    system_log: str


@dataclass
class ChromeConfig:
    exec_path: str
    profile_path: str


@dataclass
class Config:
    download: DownloadConfig
    paths: PathConfig
    chrome: ChromeConfig


class ConfigManager:
    """Load and process configs based on user platform.

    The DEFAULT_CONFIG is a nested dict, after processing, the ConfigManager.load() returns a
    Config dataclass consists of DownloadConfig, PathConfig, ChromeConfig dataclasses.
    """

    def __init__(self, config: dict[str, dict[str, Any]], config_dir: str | None = None):
        self.config = config
        self.config_dir = config_dir

    def load(self) -> Config:
        """Load configuration from files and environment."""
        system_config_dir = ConfigManager.get_system_config_dir()
        if self.config_dir is not None:  # overwrite the config_dir
            system_config_dir = Path(self.config_dir)
        system_config_dir.mkdir(parents=True, exist_ok=True)

        custom_config_path = system_config_dir / "config.yaml"
        custom_env_path = system_config_dir / ".env"

        # Load environment variables
        if custom_env_path.exists():
            load_dotenv(custom_env_path)

        # Load and merge configurations
        if custom_config_path.exists():
            with open(custom_config_path) as f:
                custom_config = yaml.safe_load(f)
                if custom_config:  # not empty
                    self.config = ConfigManager._merge_config(self.config, custom_config)

        # Check file paths
        for key, path in self.config["paths"].items():
            self.config["paths"][key] = self.resolve_path(path, system_config_dir)

        self.config["chrome"]["profile_path"] = self.resolve_path(
            self.config["chrome"]["profile_path"], system_config_dir
        )

        # Check download_dir path
        download_dir = self.config["download"].get("download_dir", "").strip()
        self.config["download"]["download_dir"] = self._get_download_dir(download_dir)

        return Config(
            download=DownloadConfig(**self.config["download"]),
            paths=PathConfig(**self.config["paths"]),
            chrome=ChromeConfig(
                exec_path=ConfigManager._get_chrome_exec_path(self.config),
                profile_path=self.config["chrome"]["profile_path"],
            ),
        )

    def resolve_path(self, path, base_dir):
        """Resolve '~', add path with base_dir if input is not absolute path."""
        path = os.path.expanduser(path)
        return os.path.join(base_dir, path) if not os.path.isabs(path) else path

    @staticmethod
    def get_system_config_dir() -> Path:
        """Return the config directory."""
        if platform.system() == "Windows":
            base = os.getenv("APPDATA", "")
        else:
            base = os.path.expanduser("~/.config")
        return Path(base) / "v2dl"

    @staticmethod
    def get_default_download_dir() -> Path:
        return Path.home() / "Downloads"

    def _get_download_dir(self, download_dir: str) -> str:
        sys_dl_dir = ConfigManager.get_default_download_dir()
        result_dir = self.resolve_path(download_dir, sys_dl_dir) if download_dir else sys_dl_dir
        result_dir = Path(result_dir)
        result_dir.mkdir(parents=True, exist_ok=True)
        return str(result_dir)

    @staticmethod
    def _get_chrome_exec_path(config_data: dict) -> str:
        current_os = platform.system()
        exec_path = config_data["chrome"]["exec_path"].get(current_os)
        if not exec_path:
            raise ValueError(f"Unsupported OS: {current_os}")
        return exec_path

    @staticmethod
    def _merge_config(base: dict[str, Any], custom: dict[str, Any]) -> dict:
        """Recursively merge custom config into base config."""
        for key, value in custom.items():
            if isinstance(value, dict) and key in base:
                ConfigManager._merge_config(base[key], value)
            else:
                base[key] = value
        return base


def parse_arguments():
    parser = argparse.ArgumentParser(description="Web scraper for albums and images.")
    parser.add_argument("url", help="URL to scrape")
    parser.add_argument(
        "--bot",
        dest="bot_type",
        default="drission",
        type=str,
        choices=["selenium", "drission"],
        required=False,
        help="Type of bot to use (default: drission)",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("-q", "--quiet", action="store_true", help="Quiet mode")
    group.add_argument("-v", "--verbose", action="store_true", help="Verbose mode")
    group.add_argument(
        "--log-level", default=None, type=int, choices=range(1, 6), help="Set log level (1~5)"
    )
    parser.add_argument("--dry-run", action="store_true", help="Dry run without downloading")
    parser.add_argument("--no-skip", action="store_true", help="Do not skip downloaded files")
    parser.add_argument("--terminate", action="store_true", help="Terminate chrome after scraping")
    args = parser.parse_args()

    if args.quiet:
        log_level = logging.ERROR
    elif args.verbose:
        log_level = logging.DEBUG
    elif args.log_level is not None:
        log_level_mapping = {
            1: logging.DEBUG,
            2: logging.INFO,
            3: logging.WARNING,
            4: logging.WARNING,
            5: logging.CRITICAL,
        }
        log_level = log_level_mapping[args.verbose]
    else:
        log_level = logging.INFO

    return args, log_level
