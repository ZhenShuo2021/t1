import os
import shutil
import logging

import pytest

from v2dl.common import BaseConfigManager, RuntimeConfig, setup_logging
from v2dl.common.const import DEFAULT_CONFIG, HEADERS
from v2dl.core import ScrapeHandler
from v2dl.utils import ImageDownloadAPI, ServiceType, TaskServiceFactory
from v2dl.web_bot import get_bot

os.environ["V2PH_USERNAME"] = "naf02905@inohm.com"  # temp account for testing
os.environ["V2PH_PASSWORD"] = "VFc8v/Mqny"  # temp account for testing

TEST_URL = "https://www.v2ph.com/album/Weekly-Big-Comic-Spirits-2016-No22-23"
# TEST_URL = "https://www.v2ph.com/album/amem784a.html"
BOT = "drission"


@pytest.fixture
def setup_test_env(tmp_path, request):
    def setup_env(service_type):
        test_url = TEST_URL
        bot_type = BOT
        dry_run = False
        terminate = True
        log_level = logging.ERROR

        logger = logging.getLogger("test_logger")
        base_config = BaseConfigManager(DEFAULT_CONFIG).load()
        base_config.paths.download_log = tmp_path / "download.log"
        base_config.download.download_dir = tmp_path / "Downloads"
        base_config.download.rate_limit = 1000
        base_config.download.min_scroll_length = base_config.download.min_scroll_length * 2
        base_config.download.max_scroll_length = base_config.download.max_scroll_length * 16 + 1

        download_service = TaskServiceFactory.create(service_type, logger, max_workers=3)

        _download_function = ImageDownloadAPI(
            HEADERS,
            base_config.download.rate_limit,
            True,
            logger,
        )

        download_function = (
            _download_function.download_async
            if service_type == ServiceType.ASYNC
            else _download_function.download
        )

        runtime_config = RuntimeConfig(
            url=test_url,
            input_file="",
            bot_type=bot_type,
            chrome_args=[],
            user_agent=None,
            terminate=terminate,
            download_service=download_service,
            download_function=download_function,
            dry_run=dry_run,
            logger=logger,
            log_level=log_level,
        )

        setup_logging(log_level, log_path=base_config.paths.system_log)
        web_bot = get_bot(runtime_config, base_config)
        scraper = ScrapeHandler(runtime_config, base_config, web_bot)

        return scraper, base_config, runtime_config

    yield setup_env

    def cleanup():
        download_dir = tmp_path / "Downloads"
        download_log = tmp_path / "download.log"

        if download_dir.exists():
            shutil.rmtree(download_dir)

        if download_log.exists():
            download_log.unlink()

    request.addfinalizer(cleanup)


@pytest.mark.parametrize("service_type", [ServiceType.ASYNC, ServiceType.THREADING])
def test_download_sync(setup_test_env, service_type):
    setup_env = setup_test_env
    scraper, base_config, runtime_config = setup_env(service_type)
    test_download_dir = base_config.download.download_dir
    valid_extensions = (".jpg", ".jpeg", ".png", ".JPG", ".JPEG", ".PNG")

    # runtime_config.logger.critical(runtime_config.download_function.__name__)

    single_page_result, _ = scraper._scrape_single_page(
        TEST_URL,
        1,
        scraper.strategies["album_image"],
        "album_image",
    )

    assert isinstance(single_page_result, list), "Single page result should be a list"
    assert len(single_page_result) > 0, "Single page should return some results"
    runtime_config.download_service.stop(30)

    # Verify directory structure
    assert os.path.exists(test_download_dir), "Download directory not created"
    subdirectories = [
        d
        for d in os.listdir(test_download_dir)
        if os.path.isdir(os.path.join(test_download_dir, d))
    ]

    assert len(subdirectories) > 0, "No subdirectory found"

    # Verify downloaded content
    download_subdir = os.path.join(test_download_dir, subdirectories[0])
    assert os.path.isdir(download_subdir), "Expected a directory but found a file"

    # Check for downloaded images
    image_files = [
        f for f in os.listdir(download_subdir) if any(f.endswith(ext) for ext in valid_extensions)
    ]
    image_files_exist = len(image_files) > 0

    assert image_files_exist, "No image found"

    # Verify image file
    if image_files_exist:
        test_image = os.path.join(download_subdir, image_files[0])
        assert os.path.getsize(test_image) > 0, "Downloaded image is empty"


if __name__ == "__main__":
    pytest.main(["-v", __file__])
