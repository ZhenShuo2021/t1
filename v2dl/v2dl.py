import logging

from .config import Config, ConfigManager, RuntimeConfig, check_input_file, parse_arguments
from .const import DEFAULT_CONFIG
from .error import ScrapeError
from .logger import setup_logging
from .scrapper import ScrapeHandler
from .utils import ThreadingService
from .web_bot import get_bot


class ScrapeManager:
    """Manage the starting and ending of the scraper."""

    def __init__(self, runtime_config: RuntimeConfig, base_config: Config, web_bot):
        self.runtime_config = runtime_config
        self.base_config = base_config

        self.web_bot = web_bot
        self.dry_run = runtime_config.dry_run
        self.logger = runtime_config.logger

        # 初始化
        self.download_service: ThreadingService = runtime_config.download_service

        if not self.dry_run:
            self.download_service.start_workers()

    def start_scraping(self):
        """Start scraping based on URL type."""
        try:
            urls = self._load_urls()
            for url in urls:
                self.runtime_config.url = url
                link_scraper = ScrapeHandler(self.runtime_config, self.base_config, self.web_bot)
                link_scraper.scrape(url, self.dry_run)
        except ScrapeError as e:
            self.logger.exception("Scraping error: '%s'", e)
        finally:
            if not self.dry_run:
                self.download_service.wait_completion()
            self.web_bot.close_driver()

    def _load_urls(self):
        """Load URLs from runtime_config (URL or txt file)."""
        if self.runtime_config.input_file:
            with open(self.runtime_config.input_file) as file:
                urls = [line.strip() for line in file if line.strip()]
        else:
            urls = [self.runtime_config.url]
        return urls


def main():
    args, log_level = parse_arguments()
    if args.input_file:
        check_input_file(args.input_file)

    app_config = ConfigManager(DEFAULT_CONFIG).load()

    setup_logging(log_level, log_path=app_config.paths.system_log)
    logger = logging.getLogger(__name__)
    download_service: ThreadingService = ThreadingService(logger, num_workers=3)

    runtime_config = RuntimeConfig(
        url=args.url,
        input_file=args.input_file,
        bot_type=args.bot_type,
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
