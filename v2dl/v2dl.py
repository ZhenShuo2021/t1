import logging
import re
from typing import ClassVar

from .config import Config, ConfigManager, RuntimeConfig, parse_arguments
from .const import DEFAULT_CONFIG
from .error import ScrapeError
from .logger import setup_logging
from .scrapper import ScraperHandler
from .utils import AlbumTracker, LinkParser, ThreadingService
from .web_bot import get_bot


class ScrapeManager:
    """Manage how to scrape the given URL."""

    # Defines the mapping from url part to scrape method.
    URL_HANDLERS: ClassVar[dict[str, str]] = {
        "album": "scrape_album",
        "actor": "scrape_album_list",
        "company": "scrape_album_list",
        "category": "scrape_album_list",
        "country": "scrape_album_list",
    }

    def __init__(self, runtime_config: RuntimeConfig, base_config: Config, web_bot):
        self.runtime_config = runtime_config
        self.config = base_config

        self.url = runtime_config.url
        self.web_bot = web_bot
        self.dry_run = runtime_config.dry_run
        self.logger = runtime_config.logger

        # 初始化
        self.path_parts, self.start_page = LinkParser.parse_input_url(runtime_config.url)
        self.download_service: ThreadingService = runtime_config.download_service
        self.link_scraper = ScraperHandler(runtime_config, base_config, web_bot)
        self.album_tracker = AlbumTracker(base_config.paths.download_log)

        if not self.dry_run:
            self.download_service.start_workers()

    def start_scraping(self):
        """Start scraping based on URL type."""
        try:
            handler = self._get_handler_method()
            handler(self.url)
        except ScrapeError as e:
            self.logger.exception("Scrapping error '%s'", e)
        finally:
            if not self.dry_run:
                self.download_service.wait_completion()
            self.web_bot.close_driver()

    def scrape_album_list(self, actor_url: str):
        """Scrape all albums in album list page."""
        album_links = self.link_scraper.scrape(actor_url, self.start_page, "album_list")
        self.logger.info("Found %d albums", len(album_links))

        for album_url in album_links:
            if self.dry_run:
                self.logger.info("[DRY RUN] Album URL: %s", album_url)
            else:
                self.scrape_album(album_url)

    def scrape_album(self, album_url: str):
        """Scrape a single album page."""
        if self.album_tracker.is_downloaded(album_url) and not self.runtime_config.no_skip:
            self.logger.info("Album %s already downloaded, skipping.", album_url)
            return

        image_links = self.link_scraper.scrape(album_url, self.start_page, "album_image")
        if image_links:
            album_name = re.sub(r"\s*\d+$", "", image_links[0][1])
            self.logger.info("Found %d images in album %s", len(image_links), album_name)

            if self.dry_run:
                for link, alt in image_links:
                    self.logger.info("[DRY RUN] Image URL: %s", link)
            else:
                self.album_tracker.log_downloaded(album_url)

    def _get_handler_method(self):
        """Get the appropriate handler method based on URL path."""
        for part in self.path_parts:
            if part in self.URL_HANDLERS:
                return getattr(self, self.URL_HANDLERS[part])
        raise ValueError(f"Unsupported URL type: {self.url}")

    def __enter__(self):
        if not self.dry_run:
            self.download_service.start_workers()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if not self.dry_run:
            self.download_service.wait_completion()
        self.web_bot.close_driver()


def main():
    args, log_level = parse_arguments()
    app_config = ConfigManager(DEFAULT_CONFIG).load()

    setup_logging(log_level, log_path=app_config.paths.system_log)
    logger = logging.getLogger(__name__)
    download_service: ThreadingService = ThreadingService(logger)

    runtime_config = RuntimeConfig(
        url=args.url,
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
