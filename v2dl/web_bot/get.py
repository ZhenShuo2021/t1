import time

from ..common import Config, RuntimeConfig
from ..utils import AccountManager, KeyManager
from .drission_bot import DrissionBot
from .selenium_bot import SeleniumBot


def get_bot(runtime_config: RuntimeConfig, app_config: Config):
    bot_classes = {"selenium": SeleniumBot, "drission": DrissionBot}

    bot_type = runtime_config.bot_type
    close_browser = runtime_config.terminate
    logger = runtime_config.logger
    key_manager = KeyManager(logger, app_config.encryption)
    account_manager = AccountManager(logger, key_manager)

    if bot_type not in bot_classes:
        raise ValueError(f"Unsupported automator type: {bot_type}")

    bot = bot_classes[bot_type](runtime_config, app_config, key_manager, account_manager)

    if bot.new_profile:
        init_new_profile(bot)
    return bot


def init_new_profile(bot):
    # visit some websites for new chrome profile
    websites = [
        "https://www.google.com",
        "https://www.youtube.com",
        "https://www.wikipedia.org",
    ]

    for url in websites:
        if isinstance(bot, DrissionBot):
            bot.page.get(url)
        elif isinstance(bot, SeleniumBot):
            bot.driver.get(url)

        time.sleep(4)
