import sys

if sys.version_info < (3, 10):
    raise ImportError(
        "You are using an unsupported version of Python. Only Python versions 3.10 and above are supported by v2dl",
    )

import sys
import logging

from .cli import cli, parse_arguments
from .common import (
    DEFAULT_CONFIG,
    Config,
    ConfigManager,
    DownloadError,
    EncryptionConfig,
    FileProcessingError,
    RuntimeConfig,
    ScrapeError,
    SecurityError,
    setup_logging,
)
from .common.const import HEADERS
from .core import ScrapeHandler, ScrapeManager
from .utils import (
    AccountManager,
    AsyncService,
    Encryptor,
    ImageDownloadAPI,
    KeyManager,
    PathUtil,
    ServiceType,
    TaskServiceFactory,
)
from .version import __version__
from .web_bot import get_bot

__all__ = [
    "__version__",
    "AccountManager",
    "AsyncService",
    "Encryptor",
    "KeyManager",
    "ScrapeHandler",
    "Config",
    "DownloadError",
    "EncryptionConfig",
    "FileProcessingError",
    "ScrapeError",
    "SecurityError",
    "ImageDownloadAPI",
    "HEADERS",
]


def main() -> int:
    args, log_level = parse_arguments()
    app_config = ConfigManager(DEFAULT_CONFIG).load()

    if args.version:
        print(f"{__version__}")  # noqa: T201
        sys.exit(0)

    if args.input_file:
        PathUtil.check_input_file(args.input_file)

    if args.account:
        cli(app_config.encryption)
    setup_logging(log_level, log_path=app_config.paths.system_log)
    logger = logging.getLogger(__name__)
    download_service = TaskServiceFactory.create(ServiceType.ASYNC, logger, max_workers=3)

    runtime_config = RuntimeConfig(
        url=args.url,
        input_file=args.input_file,
        bot_type=args.bot_type,
        chrome_args=args.chrome_args,
        user_agent=args.user_agent,
        use_chrome_default_profile=args.use_default_chrome_profile,
        terminate=args.terminate,
        download_service=download_service,
        dry_run=args.dry_run,
        logger=logger,
        log_level=log_level,
        no_skip=args.no_skip,
    )

    web_bot = get_bot(runtime_config, app_config)
    scraper = ScrapeManager(runtime_config, app_config, web_bot)
    scraper.start_scraping()

    return 0
