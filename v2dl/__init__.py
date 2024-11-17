import sys

if sys.version_info < (3, 10):
    raise ImportError(
        "You are using an unsupported version of Python. Only Python versions 3.10 and above are supported by v2dl",
    )

import sys
import logging
from argparse import Namespace as NamespaceT

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
    DownloadAPIFactory,
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


def process_input(args: NamespaceT, config: Config) -> None:
    if args.input_file:
        PathUtil.check_input_file(args.input_file)

    if args.account:
        cli(config.encryption)
    return


def create_runtime_config(
    args: NamespaceT,
    config: Config,
    logger: logging.Logger,
    log_level: int,
    service_type: ServiceType = ServiceType.THREADING,
) -> RuntimeConfig:
    """Create runtime configuration with integrated download service and function."""

    service_type = ServiceType.THREADING
    download_service = TaskServiceFactory.create(
        service_type=service_type,
        logger=logger,
        max_workers=3,
    )

    download_api = DownloadAPIFactory.create(
        service_type=service_type,
        headers=HEADERS,
        rate_limit=config.download.rate_limit,
        no_skip=args.no_skip,
        logger=logger,
    )

    download_function = (
        download_api.download_async if service_type == ServiceType.ASYNC else download_api.download
    )
    logger.critical(download_function.__name__)

    return RuntimeConfig(
        url=args.url,
        input_file=args.input_file,
        bot_type=args.bot_type,
        chrome_args=args.chrome_args,
        user_agent=args.user_agent,
        use_chrome_default_profile=args.use_default_chrome_profile,
        terminate=args.terminate,
        download_service=download_service,
        download_function=download_function,
        dry_run=args.dry_run,
        logger=logger,
        log_level=log_level,
        no_skip=args.no_skip,
    )


def main() -> int:
    args, log_level = parse_arguments()
    app_config = ConfigManager(DEFAULT_CONFIG).load()
    process_input(args, app_config)

    setup_logging(log_level, log_path=app_config.paths.system_log)
    logger = logging.getLogger(__name__)
    runtime_config = create_runtime_config(args, app_config, logger, args.log_level)

    web_bot = get_bot(runtime_config, app_config)
    scraper = ScrapeManager(runtime_config, app_config, web_bot)
    scraper.start_scraping()

    return 0
