import os
import re
import sys
import time
import asyncio
import logging
from pathlib import Path

import httpx

from .parser import LinkParser

logger = logging.getLogger()


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

    def log_downloaded(self, album_url: str) -> None:
        album_url = LinkParser.remove_page_num(album_url)
        if not self.is_downloaded(album_url):
            with open(self.album_log_path, "a") as f:
                f.write(album_url + "\n")


def threading_download_job(  # noqa: PLR0913
    task_id: str,
    url: str,
    destination: Path,
    alt: str,
    rate_limit: int,
    headers: dict[str, str],
    no_skip: bool,
    logger: logging.Logger,
) -> bool:
    try:
        # obtain album_name from task_id (the format of task_id is "album_name_index")
        album_name = task_id.rsplit("_", 1)[0]
        folder = destination / Path(album_name)
        folder.mkdir(parents=True, exist_ok=True)

        filename = re.sub(r'[<>:"/\\|?*]', "", alt)  # remove invalid characters
        file_path = folder / f"{filename}.{get_image_extension(url)}"

        if file_path.exists() and not no_skip:
            logger.info("File already exists: '%s'", file_path)
            return True

        return download_image(url, file_path, headers, rate_limit, logger)

    except Exception as e:
        logger.error("Error downloading photo %s: %s", task_id, e)
        return False


def download_album(  # noqa: PLR0913
    album_name: str,
    image_links: list[tuple[str, str]],
    destination: str,
    headers: dict[str, str],
    rate_limit: int,
    no_skip: bool,
    logger: logging.Logger,
) -> None:
    """Download images from image links.

    Save images to a folder named after the album, existing files would be skipped.

    Args:
        album_name (str): Name of album folder.
        image_links (list[tuple[str, str]]): List of tuples with image URLs and corresponding alt text for filenames.
        destination (str): Download parent directory of album folder.
        headers (dict): Download request headers.
        rate_limit (int): Download rate limits.
        no_skip (bool): Do not skip downloaded files.
        logger (logging.Logger): Logger.
    """
    folder = destination / Path(album_name)
    folder.mkdir(parents=True, exist_ok=True)

    for url, alt in image_links:
        filename = re.sub(r'[<>:"/\\|?*]', "", alt)  # Remove invalid characters
        file_path = folder / f"{filename}.{get_image_extension(url)}"

        if file_path.exists() and not no_skip:
            logger.info("File already exists: '%s'", file_path)
            continue

        # requests module will log download url
        if download_image(url, file_path, headers, rate_limit, logger):
            pass


def download_image(
    url: str,
    save_path: Path,
    headers: dict[str, str],
    rate_limit: int,
    logger: logging.Logger,
) -> bool:
    """Error control subfunction for download files.

    Return `True` for successful download, else `False`.
    """
    try:
        download(url, save_path, headers, rate_limit)
        logger.info("Downloaded: '%s'", save_path)
        return True
    except httpx.HTTPStatusError as http_err:
        logger.error("HTTP error occurred: %s", http_err)
        return False
    except Exception as e:
        logger.error("An error occurred while downloading url '%s': %s", url, e)
        return False


def download(
    url: str,
    save_path: Path,
    headers: dict[str, str] | None,
    speed_limit_kbps: int = 1536,
) -> None:
    """Download with speed limit function.

    Default speed limit is 1536 KBps (1.5 MBps).
    """
    if headers is None:
        headers = {}
    chunk_size = 1024
    speed_limit_bps = speed_limit_kbps * 1024  # Convert to bytes per second

    timeout = httpx.Timeout(10.0, read=5.0)
    with httpx.Client(timeout=timeout) as client:
        try:
            with client.stream("GET", url, headers=headers) as response:
                response.raise_for_status()  # Check if request was successful

                with open(save_path, "wb") as file:
                    start_time = time.time()
                    downloaded = 0

                    for chunk in response.iter_bytes(chunk_size=chunk_size):
                        file.write(chunk)
                        downloaded += len(chunk)

                        elapsed_time = time.time() - start_time
                        expected_time = downloaded / speed_limit_bps

                        if elapsed_time < expected_time:
                            time.sleep(expected_time - elapsed_time)
        except httpx.TimeoutException:
            logger.error("The request timed out")
        except httpx.RequestError as e:
            logger.error(f"An error occurred: {e}")


async def async_download_image_task(  # noqa: PLR0913
    task_id: str,
    url: str,
    destination: Path,
    alt: str,
    rate_limit: int,
    headers: dict[str, str],
    no_skip: bool,
    logger: logging.Logger,
) -> bool:
    """Error control wrapper function for download_image task.

    Args:
        task_id: Task identifier in format "album_name_index"
        url: URL to download from
        destination: Base directory to save downloaded files
        alt: Alternative text used as filename
        rate_limit: Download speed limit in KBps
        headers: HTTP headers for request
        no_skip: Flag to force download even if file exists
        logger: Logger instance for recording events

    Returns:
        bool: True for successful download or existing file, False for failures
    """
    try:
        # obtain album_name from task_id (the format of task_id is "album_name_index")
        album_name = task_id.rsplit("_", 1)[0]
        folder = destination / Path(album_name)
        folder.mkdir(parents=True, exist_ok=True)

        filename = re.sub(r'[<>:"/\\|?*]', "", alt)  # remove invalid characters
        file_path = folder / f"{filename}.{get_image_extension(url)}"

        if file_path.exists() and not no_skip:
            logger.info("File already exists: '%s'", file_path)
            return True

        return await async_download_image(url, file_path, headers, rate_limit, logger)

    except Exception as e:
        logger.error("Error downloading photo %s: %s", task_id, e)
        return False


async def async_download_image(
    url: str,
    save_path: Path,
    headers: dict[str, str],
    rate_limit: int,
    logger: logging.Logger,
) -> bool:
    try:
        await async_download(url, save_path, headers, rate_limit)
        logger.info("下載完成: '%s'", save_path)
        return True
    except httpx.HTTPStatusError as http_err:
        logger.error("HTTP 錯誤發生: %s", http_err)
        return False
    except Exception as e:
        logger.error("下載網址 '%s' 時發生錯誤: %s", url, e)
        return False


async def async_download(
    url: str,
    save_path: Path,
    headers: dict[str, str] | None,
    speed_limit_kbps: int = 1536,
) -> None:
    if headers is None:
        headers = {}
    chunk_size = 1024
    speed_limit_bps = speed_limit_kbps * 1024

    timeout = httpx.Timeout(10.0, read=30.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("GET", url, headers=headers) as response:
                response.raise_for_status()

                with open(save_path, "wb") as file:
                    start_time = asyncio.get_event_loop().time()
                    downloaded = 0

                    async for chunk in response.aiter_bytes(chunk_size=chunk_size):
                        file.write(chunk)
                        downloaded += len(chunk)

                        elapsed_time = asyncio.get_event_loop().time() - start_time
                        expected_time = downloaded / speed_limit_bps

                        if elapsed_time < expected_time:
                            await asyncio.sleep(expected_time - elapsed_time)
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP request fail with status code: {e.response.status_code}, message: {e}")
    except httpx.RequestError as e:
        logger.error(f"Request error: {e}")
    except Exception as e:
        logger.error(f"Unknown error: {e}")


def get_image_extension(url: str) -> str:
    """Get the extension of url.

    If there is not an extension, return default value "jpg".
    """
    image_extensions = r"(?:[^.]|^)\.(jpg|jpeg|png|gif|bmp|webp|tiff|svg)$"

    match = re.search(image_extensions, url, re.IGNORECASE)

    if match:
        return match.group(1)
    else:
        # 如果沒找到，返回預設值
        return "jpg"


def check_input_file(input_path: str) -> None:
    if input_path and not os.path.isfile(input_path):
        logging.error("Input file %s does not exist.", input_path)
        sys.exit(1)
    else:
        logging.info("Input file %s exists and is accessible.", input_path)
