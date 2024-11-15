import os
import platform
from dataclasses import dataclass
from logging import Logger
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv


@dataclass
class RuntimeConfig:
    url: str
    input_file: str
    bot_type: str
    chrome_args: list[str] | None
    user_agent: str | None
    terminate: bool
    download_service: Any
    dry_run: bool
    logger: Logger
    log_level: int
    no_skip: bool = False
    use_chrome_default_profile: bool = False


@dataclass
class EncryptionConfig:
    key_bytes: int
    salt_bytes: int
    nonce_bytes: int
    kdf_ops_limit: int
    kdf_mem_limit: int


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
    encryption: EncryptionConfig


class PathTool:
    @staticmethod
    def resolve_abs_path(path: str | Path, base_dir: str | Path) -> str | Path:
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

    @staticmethod
    def get_download_dir(download_dir: str) -> str:
        sys_dl_dir = PathTool.get_default_download_dir()
        result_dir = (
            PathTool.resolve_abs_path(download_dir, sys_dl_dir) if download_dir else sys_dl_dir
        )
        result_dir = Path(result_dir)
        result_dir.mkdir(parents=True, exist_ok=True)
        return str(result_dir)

    @staticmethod
    def get_chrome_exec_path(config_data: dict[str, Any]) -> str:
        current_os = platform.system()
        exec_path = config_data["chrome"]["exec_path"].get(current_os)
        if not exec_path:
            raise ValueError(f"Unsupported OS: {current_os}")
        if not isinstance(exec_path, str):
            raise TypeError(f"Expected a string for exec_path, got {type(exec_path).__name__}")
        return exec_path


class ConfigManager(PathTool):
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
            self.config["paths"][key] = ConfigManager.resolve_abs_path(path, system_config_dir)

        self.config["chrome"]["profile_path"] = ConfigManager.resolve_abs_path(
            self.config["chrome"]["profile_path"],
            system_config_dir,
        )

        # Check download_dir path
        download_dir = self.config["download"].get("download_dir", "").strip()
        self.config["download"]["download_dir"] = ConfigManager.get_download_dir(download_dir)

        return Config(
            download=DownloadConfig(**self.config["download"]),
            paths=PathConfig(**self.config["paths"]),
            chrome=ChromeConfig(
                exec_path=ConfigManager.get_chrome_exec_path(self.config),
                profile_path=self.config["chrome"]["profile_path"],
            ),
            encryption=EncryptionConfig(**self.config.get("encryption", self.config["encryption"])),
        )

    @staticmethod
    def _merge_config(base: dict[str, Any], custom: dict[str, Any]) -> dict[str, Any]:
        """Recursively merge custom config into base config."""
        for key, value in custom.items():
            if isinstance(value, dict) and key in base:
                ConfigManager._merge_config(base[key], value)
            else:
                base[key] = value
        return base
