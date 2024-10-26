import logging
import os
import re
import threading
import time
from pathlib import Path
from queue import Queue
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import requests
from lxml import html

from .config import Config
from .const import HEADERS


class LinkParser:
    """Tool class parses URL."""

    @staticmethod
    def parse_input_url(url):
        parsed_url = urlparse(url)
        path_parts: list[str] = parsed_url.path.split("/")
        query_params = parse_qs(parsed_url.query)
        start_page: int = int(query_params.get("page", [1])[0])  # default page=1
        return path_parts, start_page

    @staticmethod
    def parse_html(html_content: str, logger: logging.Logger) -> html.HtmlElement | None:
        if "Failed" in html_content:
            return None

        try:
            return html.fromstring(html_content)
        except Exception as e:
            logger.error("Error parsing HTML content: %s", e)
            return None

    @staticmethod
    def get_max_page(tree: html.HtmlElement) -> int:
        """Parse pagination count."""
        page_links = tree.xpath(
            '//li[@class="page-item"]/a[@class="page-link" and string-length(text()) <= 2]/@href'
        )

        if not page_links:
            return 1

        page_numbers = []
        for link in page_links:
            match = re.search(r"page=(\d+)", link)
            if match:
                page_number = int(match.group(1))
            else:
                page_number = 1
            page_numbers.append(page_number)

        return max(page_numbers)

    @staticmethod
    def add_page_num(url: str, page: int) -> str:
        parsed_url = urlparse(url)  # 解析 URL
        query_params = parse_qs(parsed_url.query)  # 解析查詢參數
        query_params["page"] = [str(page)]  # 修改頁碼

        new_query = urlencode(query_params, doseq=True)  # 組合成字串
        new_url = parsed_url._replace(query=new_query)  # 替換頁碼

        # Example
        # url = "https://example.com/search?q=test&sort=asc", page = 3
        # parsed_url: ParseResult(scheme='https', netloc='example.com', path='/search', params='', query='q=test&sort=asc', fragment='')
        # query_params: {'q': ['test'], 'sort': ['asc'], 'page': ['3']}
        # new_query: 'q=test&sort=asc&page=3'
        # new_url: ParseResult(scheme='https', netloc='example.com', path='/search', params='', query='q=test&sort=asc&page=3', fragment='')
        # urlunparse: 'https://example.com/search?q=test&sort=asc&page=3'
        return urlunparse(new_url)

    @staticmethod
    def remove_page_num(url: str) -> str:
        """remove ?page=d or &page=d from URL."""
        # Parse the URL
        parsed_url = urlparse(url)
        query_params = parse_qs(parsed_url.query)

        # Remove the 'page' parameter if it exists
        if "page" in query_params:
            del query_params["page"]

        # Rebuild the query string without 'page'
        new_query = urlencode(query_params, doseq=True)

        # Rebuild the full URL
        new_url = urlunparse(parsed_url._replace(query=new_query))
        return new_url


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


def download_album(
    album_name: str,
    image_links: list[tuple[str, str]],
    destination: str,
    rate_limit: int,
    logger: logging.Logger,
):
    """Download images from image links.

    Save images to a folder named after the album, existing files would be skipped.

    Args:
        album_name (str): Name of album folder.
        image_links (list[tuple[str, str]]): List of tuples with image URLs and corresponding alt text for filenames.
        destination (str): Download parent directory of album folder.
        rate_limit (int): Download rate limits.
        logger (logging.Logger): Logger.
    """
    folder = destination / Path(album_name)
    folder.mkdir(parents=True, exist_ok=True)

    for url, alt in image_links:
        filename = re.sub(r'[<>:"/\\|?*]', "", alt)  # Remove invalid characters
        file_path = folder / f"{filename}.jpg"

        if file_path.exists():
            logger.info("File already exists: '%s'", file_path)
            continue

        # requests module will log download url
        if download_image(url, file_path, rate_limit, logger):
            pass


def download_image(url: str, save_path: Path, rate_limit: int, logger: logging.Logger) -> bool:
    """Error control subfunction for download files.

    Return `True` for successful download, else `False`.
    """
    try:
        download(url, save_path, rate_limit)
        logger.info("Downloaded: '%s'", save_path)
        return True
    except requests.exceptions.HTTPError as http_err:
        logger.error("HTTP error occurred: %s", http_err)
        return False
    except Exception as e:
        logger.error("An error occurred: %s", e)
        return False


def download(url: str, save_path: Path, speed_limit_kbps: int = 1536) -> None:
    """Download with speed limit function.

    Default speed limit is 1536 KBps (1.5 MBps).
    """

    chunk_size = 1024
    speed_limit_bps = speed_limit_kbps * 1024  # 轉換為 bytes per second

    response = requests.get(url, stream=True, headers=HEADERS)
    response.raise_for_status()  # 確認請求成功

    with open(save_path, "wb") as file:
        start_time = time.time()
        downloaded = 0

        for chunk in response.iter_content(chunk_size=chunk_size):
            file.write(chunk)
            downloaded += len(chunk)

            elapsed_time = time.time() - start_time
            expected_time = downloaded / speed_limit_bps

            if elapsed_time < expected_time:
                time.sleep(expected_time - elapsed_time)
