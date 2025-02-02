"""
Retrieve my current apartment billing information from various websites.

Using Selenium instead of REST APIs directly because Centennial uses Cloudflare
bot mitigation, which prevents most simple REST requests from my code.
"""

import io
import os
import time
import traceback
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Callable

import pandas as pd
import pandera as pa
from pandera.typing import DataFrame, Series
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from app.installSeleniumDrivers import get_driver

APARTMENT_LOGIN_PAGE_URL = "https://centennialplaceapartments.securecafe.com/residentservices/centennial-place/userlogin.aspx"
APARTMENT_USERNAME = os.environ["CENTENNIAL_APARTMENT_USERNAME"]
APARTMENT_PASSWORD = os.environ["CENTENNIAL_APARTMENT_PASSWORD"]
ELECTRICITY_LOGGING_PAGE_URL = (
    "https://customerservice2.southerncompany.com/Billing/Home"
)
ELECTRICITY_USERNAME = os.environ["GEORGIA_POWER_USERNAME"]
ELECTRICITY_PASSWORD = os.environ["GEORGIA_POWER_PASSWORD"]
INTERNET_LOGIN_PAGE_URL = "https://customer.xfinity.com/billing/services"
INTERNET_USERNAME = os.environ["XFINITY_USERNAME"]
INTERNET_PASSWORD = os.environ["XFINITY_PASSWORD"]

# Give lots of time because these sites are garbage slow
HTTP_TIMEOUT_SECONDS = 60


class RecentCharges(pa.DataFrameModel):
    date: Series[date]
    description: Series[str]
    charge_cents: Series[int]
    payment_cents: Series[int]
    balance_cents: Series[int]


@dataclass
class MonthlyCharges:
    """The RentBot charges for a single month."""

    rent_cents: int
    utilities_cents: int


def get_monthly_charges(
    apartment: RecentCharges,
    electricity: RecentCharges,
    internet: RecentCharges,
    month: date,
) -> MonthlyCharges:
    start = date(month.year, month.month, 1)
    # TODO: get the actual last day of the month?
    end = date(month.year, month.month, 28)
    apartment_charges: RecentCharges = apartment.loc[
        (start <= apartment.date) & (apartment.date <= end)
    ]

    # TODO: Find a more robust algorithm than "the biggest charge of the month
    # is definitely always the rent"?
    rent_amt = apartment_charges.charge_cents.max()
    utility_amt = apartment_charges.charge_cents.sum() - rent_amt

    # Electricity bill is usually posted within a week of the end of the month
    elec_start = start - timedelta(days=7)
    elec_end = start + timedelta(days=7)
    electricity_charges: RecentCharges = electricity.loc[
        (elec_start <= electricity.date) & (electricity.date <= elec_end)
    ]
    utility_amt += electricity_charges.charge_cents.sum()

    # Internet bill I only fetch the most recent payment
    utility_amt += internet.charge_cents.sum()

    return MonthlyCharges(rent_cents=int(rent_amt), utilities_cents=int(utility_amt))


def retry_func(func: Callable, max_retries: int) -> Any:
    for i in range(max_retries + 1):
        try:
            return func()
        except Exception:
            print(traceback.format_exc())
            print(f"{max_retries - i} retries remaining...")
    raise RuntimeError(f"Function failed after {max_retries} retries")


def get_current_charges(max_retries: int = 3, verbose: bool = False) -> MonthlyCharges:
    start_time = time.time()
    internet_charges = retry_func(
        lambda: get_internet_recent_charges(INTERNET_USERNAME, INTERNET_PASSWORD),
        max_retries,
    )
    if verbose:
        print(f"Internet ({time.time() - start_time:.2f}s):")
        print(internet_charges)

    electricity_charges = retry_func(
        lambda: get_electricity_recent_charges(
            ELECTRICITY_USERNAME, ELECTRICITY_PASSWORD
        ),
        max_retries,
    )
    if verbose:
        print(f"Electricity ({time.time() - start_time:.2f}s):")
        print(electricity_charges)

    apartment_charges = retry_func(
        lambda: get_apartment_recent_charges(APARTMENT_USERNAME, APARTMENT_PASSWORD),
        max_retries,
    )
    if verbose:
        print(f"Apartment ({time.time() - start_time:.2f}s):")
        print(apartment_charges)

    monthly_charges = get_monthly_charges(
        apartment_charges, electricity_charges, internet_charges, datetime.now().date()
    )
    if verbose:
        print("Total:")
        print(monthly_charges)
        print(f"ELAPSED TIME: {time.time() - start_time:.2f}s")

    return monthly_charges


def _dollar_str_to_cents(s: str) -> int:
    dollars_str, cents_str = s.strip().replace("$", "").replace(",", "").split(".")
    return (100 * int(dollars_str)) + int(cents_str)


def get_internet_recent_charges(
    username: str, password: str
) -> DataFrame[RecentCharges]:
    # https://customer.xfinity.com/billing/services
    # wait for the #user button to load
    # user: #user
    # button: #sign_in
    # pass: #passwd
    # button: #sign_in
    # wait until data-testid "TransactionsHistory"
    # div data-testid="TransactionsHistory" > prism-lineitem, data-testid="transaction-history-item"
    # description: label
    # date: description, e.g. "Jan 14" (relative to current day)
    # price: label-secondary, e.g. "$105.00"
    login_page_url = INTERNET_LOGIN_PAGE_URL

    # initialize browser
    driver = get_driver()
    driver.get(login_page_url)

    WebDriverWait(driver, HTTP_TIMEOUT_SECONDS).until(
        EC.presence_of_element_located((By.ID, "user"))
    )

    # log in via login page
    user = driver.find_element(By.ID, "user")
    user.send_keys(username)

    submit = driver.find_element(By.ID, "sign_in")
    submit.click()

    WebDriverWait(driver, HTTP_TIMEOUT_SECONDS).until(
        EC.presence_of_element_located((By.ID, "passwd"))
    )

    passw = driver.find_element(By.ID, "passwd")
    passw.send_keys(password)

    submit = driver.find_element(By.ID, "sign_in")
    submit.click()

    # wait for page to load
    WebDriverWait(driver, HTTP_TIMEOUT_SECONDS).until(
        EC.presence_of_element_located(
            (By.CSS_SELECTOR, "[data-testid='TransactionsHistory']")
        )
    )

    most_recent_payment = driver.find_element(
        By.CSS_SELECTOR, "[data-testid='TransactionsHistory']"
    ).find_element(By.CSS_SELECTOR, "[data-testid='transaction-history-item']")

    today = datetime.now().date()
    day_month = (
        datetime.strptime(
            # NOTE: Adding leap year to get around ambiguous year warning
            "2020 " + most_recent_payment.get_attribute("description"),
            "%Y %b %d",
        )
        .date()
        .replace(year=today.year)
    )
    if day_month > today:
        # date must be from last year, because the same month + day with the
        # current year would be in the future
        day_month.replace(year=today.year - 1)
    charge_cents = _dollar_str_to_cents(
        most_recent_payment.get_attribute("label-secondary")
    )

    driver.quit()

    # NOTE Cheating and just taking the most recent payment as both the charge
    # and payment amount
    processed_rows = [
        {
            "date": day_month,
            "description": "",
            "charge_cents": charge_cents,
            "payment_cents": 0,
            "balance_cents": 0,  # TODO: How to get the current balance?
        },
        {
            "date": day_month,
            "description": "",
            "charge_cents": 0,
            "payment_cents": charge_cents,
            "balance_cents": 0,  # TODO: How to get the current balance?
        },
    ]
    return RecentCharges.validate(pd.DataFrame(processed_rows))


def get_electricity_recent_charges(
    username: str, password: str
) -> DataFrame[RecentCharges]:
    # https://customerservice2.southerncompany.com/Billing/Home
    # user: #mat-input-0
    # pass: #mat-input-1
    # button: name "mat-raised-button", type=submit, .mat-raised-button .mat-primary
    # wait until class .current-bill-total-due
    # div#BillHistoryTable > kendo-grid > div > table
    # If text starts with "Bill" - charge, no payment
    # If text starts with "Payment" - payment
    # Bill is posted at the end of the month it's for - e.g. on 2025-01-01, the
    # bill for December 2024 might be posted on 2024-12-27
    login_page_url = ELECTRICITY_LOGGING_PAGE_URL

    # initialize browser
    driver = get_driver()
    driver.get(login_page_url)
    WebDriverWait(driver, HTTP_TIMEOUT_SECONDS).until(
        EC.presence_of_element_located((By.ID, "mat-input-0"))
    )

    # log in via login page
    user = driver.find_element(By.ID, "mat-input-0")
    user.send_keys(username)

    passw = driver.find_element(By.ID, "mat-input-1")
    passw.send_keys(password)

    submit = driver.find_element(By.CSS_SELECTOR, ".mat-raised-button.mat-primary")
    submit.click()

    # wait for page to load
    WebDriverWait(driver, HTTP_TIMEOUT_SECONDS).until(
        EC.presence_of_element_located((By.ID, "BillHistoryTable"))
    )

    bill_history = (
        driver.find_element(By.ID, "BillHistoryTable")
        .find_element(By.TAG_NAME, "table")
        .get_attribute("outerHTML")
    )
    raw_data = pd.read_html(io.StringIO(bill_history))[0]
    driver.quit()

    processed_rows = []
    for _, row in raw_data.iterrows():
        line_type, charge = str(row.iloc[2]).split(":")
        line_type = line_type.lower().strip()
        charge = charge.strip().split("$")[1]  # get first dollar amount
        charge_cents = _dollar_str_to_cents(charge)
        processed_rows.append(
            {
                "date": datetime.strptime(row.iloc[1], "%m/%d/%y").date(),
                "description": "",
                "charge_cents": charge_cents if line_type == "bill" else 0,
                "payment_cents": charge_cents if line_type == "payment" else 0,
                "balance_cents": 0,  # TODO: How to get the current balance?
            }
        )
    return RecentCharges.validate(pd.DataFrame(processed_rows))


def get_apartment_recent_charges(
    username: str, password: str
) -> DataFrame[RecentCharges]:
    login_page_url = APARTMENT_LOGIN_PAGE_URL
    # initialize browser
    driver = get_driver()
    driver.get(login_page_url)

    # log in via login page
    reject_cookies = driver.find_element(By.ID, "onetrust-reject-all-handler")
    reject_cookies.click()

    username_input = driver.find_element(By.ID, "Username")
    username_input.send_keys(username)

    pass_input = driver.find_element(By.ID, "Password")
    pass_input.send_keys(password)

    submit = driver.find_element(By.ID, "SignIn")
    submit.click()

    # wait for page to load
    WebDriverWait(driver, HTTP_TIMEOUT_SECONDS).until(
        EC.presence_of_element_located((By.ID, "tabs"))
    )

    # navigate to recent charge activity table
    recent_activity = driver.find_element(By.ID, "LinkRecentActivity")
    recent_activity.click()

    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.ID, "PendingActivityDetails"))
    )

    recent_activity_table = driver.find_element(By.ID, "PendingActivityDetails")
    table_html = recent_activity_table.get_attribute("outerHTML")

    df = pd.read_html(io.StringIO(table_html))[0]
    driver.quit()

    return RecentCharges.validate(
        pd.DataFrame(
            {
                "date": df["Date"].apply(
                    lambda x: datetime.strptime(x, "%m/%d/%Y").date()
                ),
                "description": df["Payments and Charges"],
                "charge_cents": df["Charge"].apply(_dollar_str_to_cents),
                "payment_cents": df["Payments"].apply(_dollar_str_to_cents),
                "balance_cents": df["Balance"].apply(_dollar_str_to_cents),
            }
        )
    )


def main():
    get_current_charges(verbose=True)


if __name__ == "__main__":
    main()
