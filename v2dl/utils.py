import logging
import re
import time
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import requests
from lxml import html

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
