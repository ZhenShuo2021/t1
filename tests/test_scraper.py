import logging
import os
import time

import pytest

from v2dl.config import ConfigManager
from v2dl.const import DEFAULT_CONFIG
from v2dl.logger import setup_logging
from v2dl.v2dl import ScrapeManager
from v2dl.web_bot import get_bot

os.environ["V2PH_USERNAME"] = "naf02905@inohm.com"  # temp account for testing
os.environ["V2PH_PASSWORD"] = "VFc8v/Mqny"  # temp account for testing

TEST_URL = "https://www.v2ph.com/album/Weekly-Big-Comic-Spirits-2016-No22-23"
# TEST_URL = "https://www.v2ph.com/album/amem784a.html"
BOT = "drission"


@pytest.fixture
def setup_test_env():
    # test_download_dir = tmp_path / "test_download"
    # test_download_dir.mkdir()
    test_url = TEST_URL
    bot_type = BOT
    dry_run = False
    terminate = True

    logger = logging.getLogger("test_logger")
    logger.setLevel(logging.INFO)

    # def patched_join(*args):
    #     if args and args[0] == "download":
    #         return original_join(str(test_download_dir), *args[1:])
    #     return original_join(*args)

    # monkeypatch.setattr("os.path.join", patched_join)

    config = ConfigManager(DEFAULT_CONFIG).load()
    setup_logging(logging.INFO, log_path=config.paths.system_log)
    web_bot = get_bot(bot_type, config, terminate, logger)
    scraper = ScrapeManager(test_url, web_bot, dry_run, config, logger)

    # scraper.config.download.download_dir = str(test_download_dir)
    return scraper, scraper.config.download.download_dir


def test_download(setup_test_env):
    timeout = 60
    counter = 0
    scraper, test_download_dir = setup_test_env

    scraper.start_scraping()
    start_time = time.time()
    while True:
        counter += 1
        if time.time() - start_time > timeout or counter > timeout:
            break
        time.sleep(1)

    downloaded_files = os.path.join(test_download_dir, os.listdir(test_download_dir)[0])
    assert len(downloaded_files) > 0, "No success downloads"


if __name__ == "__main__":
    pytest.main(["-v", __file__])
