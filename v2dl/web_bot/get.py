import time

from .drission_bot import DrissionBot
from .selenium_bot import SeleniumBot


def get_bot(bot_type: str, config, close_browser, logger):
    bot_classes = {"selenium": SeleniumBot, "drission": DrissionBot}
    if bot_type not in bot_classes:
        raise ValueError(f"Unsupported automator type: {bot_type}")

    bot = bot_classes[bot_type](config, close_browser, logger)

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
