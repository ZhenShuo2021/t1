import os
import shutil
import logging
import threading
from pathlib import Path

import pytest

from v2dl import (
    DEFAULT_CONFIG,
    AsyncService,
    ConfigManager,
    RuntimeConfig,
    ScrapeManager,
    get_bot,
    setup_logging,
)

os.environ["V2PH_USERNAME"] = "naf02905@inohm.com"  # temp account for testing
os.environ["V2PH_PASSWORD"] = "VFc8v/Mqny"  # temp account for testing

TEST_URL = "https://www.v2ph.com/album/Weekly-Big-Comic-Spirits-2016-No22-23"
# TEST_URL = "https://www.v2ph.com/album/amem784a.html"
BOT = "drission"


@pytest.fixture
def setup_test_env(tmp_path, request):
    test_url = TEST_URL
    bot_type = BOT
    dry_run = False
    terminate = True
    log_level = logging.INFO

    logger = logging.getLogger("test_logger")
    config = ConfigManager(DEFAULT_CONFIG).load()
    config.paths.download_log = tmp_path / "download.log"
    config.download.download_dir = tmp_path / "Downloads"
    config.download.rate_limit = 1000
    config.download.min_scroll_step = config.download.min_scroll_length * 4
    config.download.max_scroll_step = config.download.min_scroll_length * 4 + 1

    download_service: AsyncService = AsyncService(logger)

    runtime_config = RuntimeConfig(
        url=test_url,
        input_file="",
        bot_type=bot_type,
        chrome_args=[],
        user_agent=None,
        terminate=terminate,
        download_service=download_service,
        dry_run=dry_run,
        logger=logger,
        log_level=log_level,
    )

    setup_logging(log_level, log_path=config.paths.system_log)
    web_bot = get_bot(runtime_config, config)
    scraper = ScrapeManager(runtime_config, config, web_bot)

    yield scraper, config.download.download_dir

    def cleanup():
        download_dir = Path(config.download.download_dir)
        download_log = Path(config.paths.download_log)

        if download_dir.exists():
            shutil.rmtree(download_dir)

        if download_log.exists():
            download_log.unlink()

    request.addfinalizer(cleanup)  # noqa: PT021


def test_download(setup_test_env):
    timeout = 30
    scraper, test_download_dir = setup_test_env
    valid_extensions = (".jpg", ".jpeg", ".png", ".JPG", ".JPEG", ".PNG")

    thread = threading.Thread(target=scraper.start_scraping)
    thread.start()
    thread.join(timeout)

    subdirectories = os.listdir(test_download_dir)
    assert len(subdirectories) > 0, "No subdirectory found"

    download_subdir = os.path.join(test_download_dir, subdirectories[0])
    assert os.path.isdir(download_subdir), "Expected a directory but found a file"

    image_files_exist = any(file.endswith(valid_extensions) for file in os.listdir(download_subdir))

    assert image_files_exist, "No image found"


if __name__ == "__main__":
    pytest.main(["-v", __file__])
