import logging
import os
import re
import threading
import time
from abc import ABC, abstractmethod
from enum import Enum
from queue import Queue
from typing import Generic, TypeAlias, TypeVar

from lxml import html

from .config import Config, ConfigManager, parse_arguments
from .const import BASE_URL, XPATH_ALBUM, XPATH_ALBUM_LIST, XPATH_ALTS
from .custom_logger import setup_logging
from .utils import LinkParser, download_album
from .web_bot import get_bot

AlbumLink: TypeAlias = str
ImageLink: TypeAlias = tuple[str, str]
T = TypeVar("T", AlbumLink, ImageLink)


class ScrapingType(Enum):
    """Available methods for page scaping. An alternative IDE friendly way of dict."""

    ALBUM_LIST = "album_list"
    ALBUM_IMAGE = "album_image"


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


class LinkScraper:
    """Main scraper class using strategy pattern."""

    def __init__(self, web_bot, dry_run: bool, download_service, logger: logging.Logger):
        self.web_bot = web_bot
        self.logger = logger
        self.strategies: dict[ScrapingType, ScrapingStrategy] = {
            ScrapingType.ALBUM_LIST: AlbumListStrategy(web_bot, download_service, logger),
            ScrapingType.ALBUM_IMAGE: AlbumImageStrategy(
                web_bot, download_service, logger, dry_run
            ),
        }

    def scrape_album_list(self, url: str, start_page: int) -> list[str]:
        """Convenience method for album list scraping."""
        return self.scrape_link(url, start_page, ScrapingType.ALBUM_LIST)

    def scrape_album_images(self, url: str, start_page: int) -> list[tuple[str, str]]:
        """Convenience method for album images scraping."""
        return self.scrape_link(url, start_page, ScrapingType.ALBUM_IMAGE)

    def scrape_link(self, url: str, start_page: int, scraping_type: ScrapingType) -> list[T]:
        """Scrape pages for links using the appropriate strategy."""
        strategy = self.strategies[scraping_type]
        self.logger.info(
            "Starting to scrape %s links from %s", "album" if scraping_type else "image", url
        )

        page_result: list[T] = []
        page = start_page
        consecutive_page = 0
        max_consecutive_page = 3

        while True:
            full_url = LinkParser.add_page_num(url, page)
            html_content = self.web_bot.auto_page_scroll(full_url)
            tree = LinkParser.parse_html(html_content, self.logger)

            if tree is None:
                break

            self.logger.info("Fetching content from %s", full_url)
            page_links = tree.xpath(strategy.get_xpath())

            if not page_links:
                self.logger.info(
                    "No more %s found on page %d", "albums" if scraping_type else "images", page
                )
                break

            strategy.process_page_links(page_links, page_result, tree, page)

            if page >= LinkParser.get_max_page(tree):
                self.logger.info("Reached last page, stopping")
                break

            page += 1
            consecutive_page += 1
            if consecutive_page == max_consecutive_page:
                consecutive_page = 0
                time.sleep(15)

        return page_result


class ScrapingStrategy(Generic[T], ABC):
    """Abstract base class for different scraping strategies."""

    def __init__(self, web_bot, download_service, logger: logging.Logger):
        self.web_bot = web_bot
        self.download_service = download_service
        self.logger = logger

    @abstractmethod
    def get_xpath(self) -> str:
        """Return xpath for the specific strategy."""

    @abstractmethod
    def process_page_links(
        self,
        page_links: list[str],
        page_result: list[T],
        tree: html.HtmlElement,
        page: int,
        **kwargs,
    ) -> None:
        """Process links found on the page."""


class AlbumListStrategy(ScrapingStrategy):
    """Strategy for scraping album list pages."""

    def get_xpath(self) -> str:
        return XPATH_ALBUM_LIST

    def process_page_links(
        self,
        page_links: list[str],
        page_result: list[str],
        tree: html.HtmlElement,
        page: int,
        **kwargs,
    ) -> None:
        page_result.extend([BASE_URL + album_link for album_link in page_links])
        self.logger.info("Found %d albums on page %d", len(page_links), page)


class AlbumImageStrategy(ScrapingStrategy):
    """Strategy for scraping album image pages."""

    def __init__(self, web_bot, download_service, logger: logging.Logger, dry_run: bool):
        super().__init__(web_bot, download_service, logger)
        self.dry_run = dry_run
        self.alt_counter = 0

    def get_xpath(self) -> str:
        return XPATH_ALBUM

    def process_page_links(
        self,
        page_links: list[str],
        page_result: list[tuple[str, str]],
        tree: html.HtmlElement,
        page: int,
        **kwargs,
    ) -> None:
        alts: list[str] = tree.xpath(XPATH_ALTS)

        # Handle missing alt texts
        if len(alts) < len(page_links):
            missing_alts = [str(i + self.alt_counter) for i in range(len(page_links) - len(alts))]
            alts.extend(missing_alts)
            self.alt_counter += len(missing_alts)

        page_result.extend(zip(page_links, alts))

        # Handle downloads if not in dry run mode
        if not self.dry_run:
            album_name = self._extract_album_name(alts)
            image_links = list(zip(page_links, alts))
            self.download_service.add_download_task(album_name, image_links)

        self.logger.info("Found %d images on page %d", len(page_links), page)

    @staticmethod
    def _extract_album_name(alts: list[str]) -> str:
        album_name = next((alt for alt in alts if not alt.isdigit()), None)
        if album_name:
            album_name = re.sub(r"\s*\d*$", "", album_name).strip()
        if not album_name:
            album_name = BASE_URL.rstrip("/").split("/")[-1]
        return album_name


class AlbumTracker:
    """Download log in units of albums."""

    def __init__(self, download_log: str):
        self.album_log_path = download_log

    def is_downloaded(self, album_url: str) -> bool:
        if os.path.exists(self.album_log_path):
            with open(self.album_log_path) as f:
                downloaded_albums = f.read().splitlines()
            return album_url in downloaded_albums
        return False

    def log_downloaded(self, album_url: str):
        album_url = LinkParser.remove_page_num(album_url)
        if not self.is_downloaded(album_url):
            with open(self.album_log_path, "a") as f:
                f.write(album_url + "\n")


class DownloadService:
    """Initialize multiple threads with a queue for downloading."""

    def __init__(self, config: Config, logger: logging.Logger, num_workers: int = 1):
        self.download_queue: Queue = Queue()
        self.config = config
        self.logger = logger
        self.num_workers = num_workers  # one worker is enough, too many workers would be blocked
        self.worker_threads: list[threading.Thread] = []

    def start_workers(self):
        """Start up multiple worker threads to listen download needs."""
        for _ in range(self.num_workers):
            worker = threading.Thread(target=self._download_worker, daemon=True)
            self.worker_threads.append(worker)
            worker.start()

    def _download_worker(self):
        """Worker function to process downloads from the queue."""
        dest = self.config.download.download_dir
        rate = self.config.download.rate_limit
        while True:  # run until receiving exit signal
            album_name, page_image_links = self.download_queue.get()  # get job from queue
            if album_name is None:
                break  # exit signal received
            download_album(album_name, page_image_links, dest, rate, self.logger)
            self.download_queue.task_done()

    def add_download_task(self, album_name: str, image_links: list[tuple[str, str]]):
        """Add task to queue."""
        self.download_queue.put((album_name, image_links))

    def wait_completion(self):
        """Block until all tasks are done and stop all workers."""
        self.download_queue.join()  # Block until all tasks are done.

        # Signal all workers to exit
        for _ in range(self.num_workers):
            self.download_queue.put((None, None))

        # Wait for all worker threads to finish
        for worker in self.worker_threads:
            worker.join()


class ScrapeError(Exception):
    pass


class FileProcessingError(Exception):
    pass


class DownloadError(Exception):
    pass


def main():
    args, log_level = parse_arguments()
    config = ConfigManager().load()
    setup_logging(log_level, log_path=config.paths.system_log)
    logger = logging.getLogger(__name__)

    web_bot = get_bot(args.bot_type, config, args.terminate, logger)
    scraper = ScrapeManager(args.url, web_bot, args.dry_run, config, logger)
    scraper.start_scraping()
