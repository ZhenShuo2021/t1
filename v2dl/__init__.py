# v2dl/__init__.py
import logging
import sys

from .cli.account_cli import cli
from .cli.option import parse_arguments
from .common.config import Config, ConfigManager, RuntimeConfig
from .common.const import DEFAULT_CONFIG
from .common.error import DownloadError, FileProcessingError, ScrapeError
from .common.logger import setup_logging
from .core.scrapper import ScrapeHandler, ScrapeManager
from .utils import ThreadingService, check_input_file
from .version import __version__
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
    "__version__",
]


def main():
    args, log_level = parse_arguments()

    if args.version:
        print(f"{__version__}")
        sys.exit(0)

    if args.input_file:
        check_input_file(args.input_file)

    if args.account:
        cli()

    app_config = ConfigManager(DEFAULT_CONFIG).load()

    setup_logging(log_level, log_path=app_config.paths.system_log)
    logger = logging.getLogger(__name__)
    download_service: ThreadingService = ThreadingService(logger, num_workers=3)

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
