import random
import subprocess
import sys
import time
from subprocess import Popen

from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as EC  # noqa: N812
from selenium.webdriver.support.ui import WebDriverWait

from ..common.const import SELENIUM_AGENT
from .base import BaseBehavior, BaseBot, BaseScroll

DEFAULT_BOT_OPT = [
    "--remote-debugging-port=9222",
    "--disable-gpu",
    "--disable-infobars",
    "--disable-extensions",
    "--disable-dev-shm-usage",
    # "--disable-blink-features",
    # "--disable-blink-features=AutomationControlled",
    "--start-maximized",
    # "--ignore-certificate-errors",
]


class SeleniumBot(BaseBot):
    def __init__(self, runtime_config, base_config, key_manager, account_manager):
        super().__init__(runtime_config, base_config, key_manager, account_manager)
        self.init_driver()
        self.scroller = SelScroll(self.driver, self.config, self.logger)
        self.cloudflare = SelCloudflareHandler(self.driver, self.logger)

    def init_driver(self):
        self.driver: WebDriver
        self.chrome_process: Popen
        options = Options()

        chrome_path = [self.config.chrome.exec_path]
        # "or" returns the first True element
        subprocess_cmd = chrome_path + (self.runtime_config.chrome_args or DEFAULT_BOT_OPT)
        subprocess_cmd = [*subprocess_cmd, self.runtime_config.user_agent or SELENIUM_AGENT]

        if not self.runtime_config.use_chrome_default_profile:
            user_data_dir = self.prepare_chrome_profile()
            subprocess_cmd.append(f"--user-data-dir={user_data_dir}")

        self.chrome_process = subprocess.Popen(subprocess_cmd)

        options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
        try:
            self.driver = webdriver.Chrome(service=Service(), options=options)
        except Exception as e:
            self.logger.error("Unable to start Selenium WebDriver: %s", e)
            sys.exit("Unable to start Selenium WebDriver")

        # width = random.randint(1024, 1920)
        # height = random.randint(768, 1080)
        # self.driver.set_window_size(1920, 1080)

    def close_driver(self):
        pass
        # if self.close_browser:
        #     self.driver.quit()
        #     self.chrome_process.terminate()

    def auto_page_scroll(
        self, url: str, max_retry: int = 3, page_sleep: int = 5, fast_scroll: bool = False
    ) -> str:
        """Scroll page automatically with retries and Cloudflare challenge handle.

        The main function of this class.

        Args:
            url (str): Target URL
            max_retry (int): Maximum number of retry attempts. Defaults to 3
            page_sleep (int): The sleep time after reaching page bottom
            fast_scroll (bool): Whether to use fast scroll. Might be blocked by Cloudflare

        Returns:
            str: Page HTML content or error message
        """
        response: str = ""
        for attempt in range(max_retry):
            try:
                self.driver.get(url)
                SelBehavior.random_sleep(0.1, 0.5)

                if not self.handle_redirection_fail(url, max_retry, page_sleep):
                    self.logger.error(
                        "Reconnection fail for URL %s. Please check your network status.", url
                    )
                    break

                if self.cloudflare.handle_simple_block(attempt, max_retry):
                    continue

                # WebDriverWait(self.driver, 5).until(
                #     EC.presence_of_element_located((By.CSS_SELECTOR, "div.album-photo.my-2"))
                # )

                # main business
                self.handle_login()
                self.driver.execute_script("document.body.style.zoom='75%'")
                self.scroller.scroll_to_bottom()
                SelBehavior.random_sleep(5, 15)

                response = self.driver.page_source
                break

            except Exception as e:
                self.logger.exception(
                    "Request failed for URL %s - Attempt %d/%d. Error: %s",
                    url,
                    attempt + 1,
                    max_retry,
                    e,
                )

            self.logger.debug("Scrolling finished, pausing to avoid blocking")
            SelBehavior.random_sleep(page_sleep, page_sleep + 5)

        if not response:
            error_template = "Failed to retrieve URL after {} attempts: '{}'"
            error_msg = error_template.format(max_retry, url)
            self.logger.error(error_msg)
            return error_msg
        return response

    def handle_redirection_fail(self, url: str, max_retry: int, sleep_time: int) -> bool:
        if self.driver.current_url == url:
            return True
        retry = 1
        while retry <= max_retry:
            self.logger.error("Connection failed - Attempt %d/%d", retry, max_retry)
            SelBehavior.random_sleep(sleep_time, sleep_time + 5 * random.uniform(1, retry * 5))

            if self.cloudflare.handle_simple_block(retry, max_retry):
                self.logger.critical("Failed to solve Cloudflare turnstile challenge")
                continue

            self.driver.get(url)
            retry += 1
            if self.driver.current_url == url:
                return True

        return self.driver.current_url == url

    def handle_login(self):
        success = False
        if self.driver.find_elements(
            By.XPATH, "//h1[@class='h4 text-secondary mb-4 login-box-msg']"
        ):
            self.logger.info("Login page detected - Starting login process")
            try:
                self.email, self.password = self.account_manager.random_pick(self.private_key)
                if self.email is None or self.password is None:
                    self.logger.critical("Email and password not provided")
                    sys.exit("Automated login failed.")

                email_field = self.driver.find_element(By.ID, "email")
                password_field = self.driver.find_element(By.ID, "password")
                BaseBehavior.random_sleep(0.5, 1)

                # SelBehavior.human_like_mouse_movement(self.driver, email_field)
                password_field.send_keys(Keys.SHIFT, Keys.TAB)
                BaseBehavior.random_sleep(0.5, 1)
                SelBehavior.human_like_type(email_field, self.email)
                SelBehavior.random_sleep(0.01, 0.3)

                # SelBehavior.human_like_mouse_movement(self.driver, password_field)
                # SelBehavior.human_like_click(self.driver, email_field)
                email_field.send_keys(Keys.TAB)
                SelBehavior.human_like_type(password_field, self.password)
                SelBehavior.random_sleep(0.01, 0.5)

                # try:
                #     remember_checkbox = self.driver.find_element(By.ID, "remember")
                #     if not remember_checkbox.is_selected():
                #         SelBehavior.human_like_click(self.driver, remember_checkbox)
                # except NoSuchElementException:
                #     self.logger.warning("Remember me checkbox not found")

                try:
                    self.cloudflare.handle_cloudflare_recaptcha()
                except Exception as e:
                    self.logger.exception("Error handling Cloudflare reCAPTCHA: %s", e)

                self.driver.find_element(
                    By.XPATH, '//button[@type="submit" and @class="btn btn-primary btn-block"]'
                ).click()

                SelBehavior.random_sleep(3, 5)

                if not self.driver.find_elements(
                    By.XPATH, "//h1[@class='h4 text-secondary mb-4 login-box-msg']"
                ):
                    self.logger.info("Login successful")
                    success = True
                else:
                    self.logger.error("Login failed - Checking for error messages")
                    self.check_login_errors()

            except NoSuchElementException as e:
                self.logger.error("Login form element not found: %s", e)
            except TimeoutException as e:
                self.logger.error("Timeout waiting for element: %s", e)
            except Exception as e:
                self.logger.error("Unexpected error during login: %s", e)
        else:
            success = True
        if not success:
            self.logger.critical("Automated login failed. Please login yourself.")
            sys.exit("Automated login failed.")

    def check_login_errors(self):
        error_messages = self.driver.find_elements(By.CLASS_NAME, "errorMessage")
        if error_messages:
            for message in error_messages:
                self.logger.error("Login error: %s", message.text)
        else:
            self.logger.warning(
                "No specific error message found. Login might have failed for unknown reasons."
            )


class SelCloudflareHandler:
    """Handles Cloudflare protection detection and bypass attempts.

    Includes methods for dealing with various Cloudflare challenges.
    """

    def __init__(self, driver: WebDriver, logger):
        self.driver = driver
        self.logger = logger

    def handle_simple_block(self, attempt: int, retries: int) -> bool:
        """check and handle Cloudflare challenge."""
        blocked = False
        if self.is_simple_blocked():
            self.logger.info(
                "Detected Cloudflare challenge, attempting to solve... Attempt %d/%d",
                attempt + 1,
                retries,
            )
            self.handle_cloudflare_turnstile()
            blocked = True
        return blocked

    def handle_hard_block(self) -> bool:
        """Check, log critical, and return whether blocked or not.

        This is a cloudflare WAF full page block.
        """
        blocked = False
        if self.is_hard_block():
            self.logger.critical("Hard block detected by Cloudflare - Unable to proceed")
            blocked = True
        return blocked

    def is_simple_blocked(self) -> bool:
        title_check = any(text in self.driver.title for text in ["請稍候...", "Just a moment..."])
        page_source_check = "Checking your" in self.driver.page_source
        return title_check or page_source_check

    def is_hard_block(self) -> bool:
        is_blocked = "Attention Required! | Cloudflare" in self.driver.title
        if is_blocked:
            self.logger.critical("Cloudflare hard block detected")
        return is_blocked

    def handle_cloudflare_turnstile(self):
        try:
            iframe = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((
                    By.XPATH,
                    "//iframe[contains(@src, 'challenges.cloudflare.com')]",
                ))
            )
            self.driver.switch_to.frame(iframe)

            checkbox = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.ID, "cf-turnstile-response"))
            )
            SelBehavior.human_like_click(self.driver, checkbox)

            if "Select all squares with" in self.driver.page_source:
                self.solve_image_captcha()

            self.driver.switch_to.default_content()
            SelBehavior.random_sleep(10, 20)
        except (TimeoutException, NoSuchElementException):
            self.logger.error("Unable to solve Cloudflare challenge.")

    def handle_cloudflare_recaptcha(self):
        try:
            recaptcha_checkbox = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//input[@type='checkbox']"))
            )
            SelBehavior.human_like_click(self.driver, recaptcha_checkbox)

            verify_button = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//span[contains(text(), '驗證您是人類')]"))
            )
            SelBehavior.human_like_click(self.driver, verify_button)

            SelBehavior.random_sleep(3, 5)
        except (TimeoutException, NoSuchElementException) as e:
            self.logger.warning(
                "reCAPTCHA checkbox or verify button not found or unable to interact: %s", e
            )

    def solve_image_captcha(self):
        raise NotImplementedError


class SelBehavior(BaseBehavior):
    @staticmethod
    def human_like_mouse_movement(driver, element):
        action = ActionChains(driver)
        action.move_by_offset(random.randint(-100, 100), random.randint(-100, 100))
        action.move_to_element_with_offset(
            element, random.randint(-10, 10), random.randint(-10, 10)
        )
        action.pause(random.uniform(0.1, 0.3))
        action.move_to_element(element)
        action.perform()
        SelBehavior.random_sleep(*BaseBehavior.pause_time)

    @staticmethod
    def human_like_click(driver, element):
        SelBehavior.human_like_mouse_movement(driver, element)
        action = ActionChains(driver)
        action.click()
        action.perform()
        SelBehavior.random_sleep(*BaseBehavior.pause_time)

    @staticmethod
    def human_like_type(element, text):
        for char in text:
            element.send_keys(char)
            time.sleep(random.uniform(0.001, 0.2))
        SelBehavior.random_sleep(*BaseBehavior.pause_time)


class SelScroll(BaseScroll):
    def __init__(self, driver: WebDriver, config, logger):
        super().__init__(config, logger)
        self.driver = driver

    def scroll_to_bottom(self):
        max_attempts = 10
        attempts = 0
        last_position = -123459
        scroll_length = lambda: random.randint(
            self.config.download.min_scroll_length,
            self.config.download.max_scroll_length,
        )

        while attempts < max_attempts:
            SelBehavior.random_sleep(1, 2)
            scroll = scroll_length()
            self.logger.debug(
                "Current position: %d, scrolling down by %d pixels", last_position, scroll
            )
            self.driver.execute_script(f"window.scrollBy({{top: {scroll}, behavior: 'smooth'}});")
            new_position = self.driver.execute_script("return window.pageYOffset;")
            if new_position == last_position:
                break
            last_position = new_position
            attempts += 1

    def old_scroll_to_bottom(self):
        self.logger.info("Start scrolling the page")
        scroll_attempts = 0
        max_attempts = 45

        scroll_pos_init = self.driver.execute_script("return window.pageYOffset;")
        step_scroll = random.randint(
            self.config.download.min_scroll_length,
            self.config.download.max_scroll_length,
        )

        while scroll_attempts < max_attempts:
            scroll_attempts += 1

            self.driver.execute_script(f"window.scrollBy(0, {step_scroll});")
            scroll_pos_end = self.driver.execute_script("return window.pageYOffset;")
            time.sleep(0.75)

            if scroll_pos_init >= scroll_pos_end:
                self.logger.debug("Reached the bottom of the page")
                break

            scroll_pos_init = scroll_pos_end

            step_scroll = random.randint(
                self.config.download.min_scroll_length, self.config.download.max_scroll_length
            )

            self.wait_for_content_load()

            self.successive_scroll_count += 1
            if self.successive_scroll_count >= self.max_successive_scrolls:
                pause_time = random.uniform(3, 7)
                self.logger.debug(
                    "Scrolled %d times, pausing for %.2f seconds",
                    self.successive_scroll_count,
                    pause_time,
                )
                time.sleep(pause_time)
                self.successive_scroll_count = 0
                self.max_successive_scrolls = random.randint(3, 7)

        if scroll_attempts == max_attempts:
            self.logger.info(
                "Reached maximum attempts (%d), scrolling finished, may not have fully reached the bottom",
                max_attempts,
            )
        else:
            self.logger.info("Page scroll completed")

    def perform_scroll_action(self):
        action = random.choices(
            ["scroll_down", "scroll_up", "pause", "jump"],
            weights=[0.7, 0.1, 0.1, 0.1],
        )[0]

        current_position = self.get_scroll_position()

        if action == "scroll_down":
            scroll_length = random.randint(
                self.config.download.min_scroll_length,
                self.config.download.max_scroll_length,
            )
            target_position = current_position + scroll_length
            self.logger.debug("Trying to scroll down %d pixels", scroll_length)
            actual_position = self.safe_scroll(target_position)
            self.logger.debug("Actually scrolled to %d pixels", actual_position)
            time.sleep(random.uniform(*BaseBehavior.pause_time))
        elif action == "scroll_up":
            scroll_length = random.randint(
                self.config.download.min_scroll_length,
                self.config.download.max_scroll_length,
            )
            target_position = max(0, current_position - scroll_length)
            self.logger.debug("Trying to scroll up %d pixels", scroll_length)
            actual_position = self.safe_scroll(target_position)
            self.logger.debug("Actually scrolled to %d pixels", actual_position)
        elif action == "pause":
            pause_time = random.uniform(1, 3)
            self.logger.debug("Pausing for %.2f seconds", pause_time)
            time.sleep(pause_time)
        elif action == "jump":
            jump_position = current_position + random.randint(100, 500)
            self.logger.debug("Trying to jump to position %d", jump_position)
            actual_position = self.safe_scroll(jump_position)
            self.logger.debug("Actually jumped to %d", actual_position)

    def safe_scroll(self, target_position):
        current_position = self.get_scroll_position()
        step = random.uniform(
            self.config.download.min_scroll_step,
            self.config.download.max_scroll_step,
        )
        # step = 50 if target_position > current_position else -50
        # while abs(current_position - target_position) > abs(step):

        while abs(current_position - target_position) > step:
            self.driver.execute_script(f"window.scrollTo(0, {current_position + step});")
            time.sleep(random.uniform(0.01, 0.2))
            new_position = self.get_scroll_position()
            if new_position == current_position:
                self.logger.debug(
                    "Cannot continue scrolling, target: %d, current: %d",
                    target_position,
                    current_position,
                )
                break
            current_position = new_position
        self.driver.execute_script(f"window.scrollTo(0, {target_position});")
        return self.get_scroll_position()

    def get_scroll_position(self):
        return self.driver.execute_script("return window.pageYOffset")

    def get_page_height(self):
        return self.driver.execute_script("return document.body.scrollHeight")

    def wait_for_content_load(self):
        try:
            WebDriverWait(self.driver, 5).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
        except TimeoutException:
            self.logger.warning("Timeout waiting for new content to load")
