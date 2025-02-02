"""
Script to initialize a Selenium driver and then close it immediately.

This is used so that we can make sure all the Selenium browser stuff is
pre-installed and doesn't need to be fetched on a cold start and/or first
request in Cloud Run.
"""

from selenium.webdriver.chrome.webdriver import WebDriver
from seleniumbase import Driver

CHROMIUM_ARGS = "disable-extensions,disable-gpu,no-sandbox"


def get_driver() -> WebDriver:
    return Driver(uc=True, headless=True, chromium_arg=CHROMIUM_ARGS)


if __name__ == "__main__":
    driver = get_driver()
    driver.quit()
