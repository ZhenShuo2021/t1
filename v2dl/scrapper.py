import re
import time
from abc import ABC, abstractmethod
from typing import ClassVar, Generic, TypeAlias, TypeVar

from lxml import html

from .config import Config, RuntimeConfig
from .const import BASE_URL, XPATH_ALBUM, XPATH_ALBUM_LIST, XPATH_ALTS
from .utils import LinkParser, threading_download_job

# Manage return types of each scraper here
AlbumLink: TypeAlias = str
ImageLink: TypeAlias = tuple[str, str]
LinkType = TypeVar("LinkType", AlbumLink, ImageLink)


class LinkScraper:
    """Main scraper class using strategy pattern.

    methods buffer_xxx are buffer methods used to avoid typing error.
    """

    # Defines the mapping from string to scraping method.
    SCRAPE_TYPE: ClassVar[dict[str, str]] = {
        "ALBUM_LIST": "album_list",
        "ALBUM_IMAGE": "album_image",
    }

    def __init__(self, runtime_config: RuntimeConfig, base_config: Config, web_bot):
        self.web_bot = web_bot
        self.logger = runtime_config.logger
        self.strategies: dict[str, ScrapingStrategy] = {
            self.SCRAPE_TYPE["ALBUM_LIST"]: AlbumListStrategy(runtime_config, base_config, web_bot),
            self.SCRAPE_TYPE["ALBUM_IMAGE"]: AlbumImageStrategy(
                runtime_config, base_config, web_bot
            ),
        }

    def buffer_album_list(self, url: str, start_page: int, **kwargs) -> list[AlbumLink]:
        """Entry and buffer method for album list scraping."""
        return self._scrape_link(url, start_page, self.SCRAPE_TYPE["ALBUM_LIST"], **kwargs)

    def buffer_album_images(self, url: str, start_page: int, **kwargs) -> list[ImageLink]:
        """Entry and buffer method for Album images scraping."""
        return self._scrape_link(url, start_page, self.SCRAPE_TYPE["ALBUM_IMAGE"], **kwargs)

    def _scrape_link(
        self,
        url: str,
        start_page: int,
        scraping_type: str,
        **kwargs,
    ) -> list[LinkType]:
        """Scrape pages for links using the appropriate strategy."""
        strategy = self.strategies[scraping_type]
        self.logger.info(
            "Starting to scrape %s links from %s", "album" if scraping_type else "image", url
        )

        page_result: list[LinkType] = []
        page = start_page

        while True:
            full_url = LinkParser.add_page_num(url, page)
            html_content = self.web_bot.auto_page_scroll(full_url)
            tree = LinkParser.parse_html(html_content, self.logger)

            if tree is None:
                break

            # log entering a page
            self.logger.info("Fetching content from %s", full_url)
            page_links = tree.xpath(strategy.get_xpath())

            # log no images
            if not page_links:
                self.logger.info(
                    "No more %s found on page %d", "albums" if scraping_type else "images", page
                )
                break

            strategy.process_page_links(page_links, page_result, tree, page)

            if page >= LinkParser.get_max_page(tree):
                self.logger.info("Reach last page, stopping")
                break

            page = self._handle_pagination(page, **kwargs)

        return page_result

    def _handle_pagination(
        self,
        current_page: int,
        max_consecutive_page: int = 3,
        consecutive_sleep: int = 15,
    ) -> int:
        """Handle pagination logic including sleep for consecutive pages."""
        next_page = current_page + 1
        if next_page % max_consecutive_page == 0:
            time.sleep(consecutive_sleep)
        return next_page


class ScrapingStrategy(Generic[LinkType], ABC):
    """Abstract base class for different scraping strategies."""

    def __init__(self, runtime_config: RuntimeConfig, base_config: Config, web_bot):
        self.runtime_config = runtime_config
        self.config = base_config
        self.web_bot = web_bot
        self.download_service = runtime_config.download_service
        self.logger = runtime_config.logger

    @abstractmethod
    def get_xpath(self) -> str:
        """Return xpath for the specific strategy."""

    @abstractmethod
    def process_page_links(
        self,
        page_links: list[str],
        page_result: list[LinkType],
        tree: html.HtmlElement,
        page: int,
        **kwargs,
    ) -> None:
        """Process links found on the page."""


class AlbumListStrategy(ScrapingStrategy[AlbumLink]):
    """Strategy for scraping album list pages."""

    def get_xpath(self) -> str:
        return XPATH_ALBUM_LIST

    def process_page_links(
        self,
        page_links: list[str],
        page_result: list[AlbumLink],
        tree: html.HtmlElement,
        page: int,
        **kwargs,
    ) -> None:
        page_result.extend([BASE_URL + album_link for album_link in page_links])
        self.logger.info("Found %d albums on page %d", len(page_links), page)


class AlbumImageStrategy(ScrapingStrategy[ImageLink]):
    """Strategy for scraping album image pages."""

    def __init__(self, runtime_config: RuntimeConfig, base_config: Config, web_bot):
        super().__init__(runtime_config, base_config, web_bot)
        self.dry_run = runtime_config.dry_run
        self.alt_counter = 0

    def get_xpath(self) -> str:
        return XPATH_ALBUM

    def process_page_links(
        self,
        page_links: list[str],
        page_result: list[ImageLink],
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
            self.download_service.add_task(
                task_id="Error processing task",
                params=(
                    album_name,
                    image_links,
                    self.config.download.download_dir,
                    self.config.download.rate_limit,
                    self.runtime_config.no_skip,
                    self.logger,
                ),
                job=threading_download_job,
            )

        self.logger.info("Found %d images on page %d", len(page_links), page)

    @staticmethod
    def _extract_album_name(alts: list[str]) -> str:
        album_name = next((alt for alt in alts if not alt.isdigit()), None)
        if album_name:
            album_name = re.sub(r"\s*\d*$", "", album_name).strip()
        if not album_name:
            album_name = BASE_URL.rstrip("/").split("/")[-1]
        return album_name
