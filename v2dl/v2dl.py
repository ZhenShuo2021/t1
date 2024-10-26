import logging
import re

from .config import Config, ConfigManager, parse_arguments
from .custom_logger import setup_logging
from .scrapper import LinkScraper, ScrapingType
from .utils import AlbumTracker, DownloadService, LinkParser
from .web_bot import get_bot


class ScrapeManager:
    """Manage how to scrape the given URL."""

    def __init__(self, url: str, web_bot, dry_run: bool, config: Config, logger: logging.Logger):
        self.url = url
        self.path_parts, self.start_page = LinkParser.parse_input_url(url)

        self.web_bot = web_bot
        self.dry_run = dry_run
        self.config = config
        self.logger = logger

        # 初始化
        self.download_service = DownloadService(config, logger)
        self.link_scraper = LinkScraper(web_bot, dry_run, self.download_service, logger)
        self.album_tracker = AlbumTracker(config.paths.download_log)

        if not dry_run:
            self.download_service.start_workers()

    def start_scraping(self):
        album_list_name = {"actor", "company", "category", "country"}
        try:
            if "album" in self.path_parts:
                self.scrape_album(self.url)
            elif any(part in album_list_name for part in self.path_parts):
                self.scrape_album_list(self.url)
            else:
                raise ValueError(f"Unsupported URL type: {self.url}")
        finally:
            if not self.dry_run:
                self.download_service.wait_completion()
            self.web_bot.close_driver()

    def scrape_album_list(self, actor_url: str):
        """Scrape all albums in album list page."""
        album_links = self.link_scraper.scrape_link(
            actor_url, self.start_page, ScrapingType.ALBUM_LIST
        )
        valid_album_links = [album_url for album_url in album_links if isinstance(album_url, str)]
        self.logger.info("Found %d albums", len(valid_album_links))

        for album_url in valid_album_links:
            if self.dry_run:
                self.logger.info("[DRY RUN] Album URL: %s", album_url)
            else:
                self.scrape_album(album_url)

    def scrape_album(self, album_url: str):
        """Scrape a single album page."""
        if self.album_tracker.is_downloaded(album_url):
            self.logger.info("Album %s already downloaded, skipping.", album_url)
            return

        image_links = self.link_scraper.scrape_album_images(album_url, self.start_page)
        if image_links:
            album_name = re.sub(r"\s*\d+$", "", image_links[0][1])
            self.logger.info("Found %d images in album %s", len(image_links), album_name)

            if self.dry_run:
                for link, alt in image_links:
                    self.logger.info("[DRY RUN] Image URL: %s", link)
            else:
                self.album_tracker.log_downloaded(album_url)


def main():
    args, log_level = parse_arguments()
    config = ConfigManager().load()
    setup_logging(log_level, log_path=config.paths.system_log)
    logger = logging.getLogger(__name__)

    web_bot = get_bot(args.bot_type, config, args.terminate, logger)
    scraper = ScrapeManager(args.url, web_bot, args.dry_run, config, logger)
    scraper.start_scraping()
