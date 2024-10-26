import logging
import re
import time
from abc import ABC, abstractmethod
from enum import Enum
from typing import Generic, TypeAlias, TypeVar

from lxml import html

from .const import BASE_URL, XPATH_ALBUM, XPATH_ALBUM_LIST, XPATH_ALTS
from .utils import LinkParser

AlbumLink: TypeAlias = str
ImageLink: TypeAlias = tuple[str, str]
T = TypeVar("T", AlbumLink, ImageLink)


class ScrapingType(Enum):
    """Available methods for page scaping. An alternative IDE friendly way of dict."""

    ALBUM_LIST = "album_list"
    ALBUM_IMAGE = "album_image"


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
