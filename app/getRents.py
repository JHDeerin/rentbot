"""
Retrieve my current apartment billing information from various websites.

Using Selenium for Centennial (Cloudflare bot mitigation + email-OTP 2FA) and
Xfinity, and a REST-based library for Georgia Power.
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import re
import time
import traceback
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Optional

import aiohttp
import pandas as pd
import pandera as pa
from pandera.typing import DataFrame, Series
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from app.email_otp import fetch_otp
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


def get_current_charges(max_retries: int = 1, verbose: bool = False) -> MonthlyCharges:
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
    print("Loaded page")

    WebDriverWait(driver, HTTP_TIMEOUT_SECONDS).until(
        EC.presence_of_element_located((By.ID, "user"))
    )
    print("User page started")

    # log in via login page
    user = driver.find_element(By.ID, "user")
    print("Found user element")
    user.send_keys(username)
    print("Typed user")

    submit = driver.find_element(By.ID, "sign_in")
    print("Found sign_in button")
    submit.click()
    print("Clicked sign_in button")

    WebDriverWait(driver, HTTP_TIMEOUT_SECONDS).until(
        EC.presence_of_element_located((By.ID, "passwd"))
    )
    print("Found passwd")

    passw = driver.find_element(By.ID, "passwd")
    passw.send_keys(password)
    print("Typed passwd")

    submit = driver.find_element(By.ID, "sign_in")
    print("Found sign_in button")
    submit.click()
    print("Clicked sign_in button")

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


async def _fetch_electricity_monthly_records(
    username: str,
    password: str,
) -> list:
    """
    Call Southern Company's MPUData Monthly endpoint via the JWT auth flow and
    return a list of {"date": date, "cost": float} records for each month of
    history the API returns.

    Matches what apearson/southern-company-api's getMonthlyData does: parses
    chartData.series.usage.data[i] for dates, chartData.series.cost.data[i].y
    for the dollar cost of that month.
    """
    from southern_company_api import SouthernCompanyAPI

    async with aiohttp.ClientSession() as session:
        api = SouthernCompanyAPI(username, password, session)
        await api.connect()  # populates _jwt and _accounts

        if not api._accounts:
            raise RuntimeError("Southern Company login returned no accounts")

        # Pick the Georgia Power account; fall back to the first primary account.
        ga_accounts = [a for a in api._accounts if a.company.name == "GPC"]
        account = ga_accounts[0] if ga_accounts else api._accounts[0]

        url = (
            "https://customerservice2api.southerncompany.com/api/MyPowerUsage/"
            f"MPUData/{account.number}/Monthly?OPCO={account.company.name}"
        )
        headers = {"Authorization": f"bearer {api._jwt}"}
        async with session.get(url, headers=headers) as resp:
            if resp.status != 200:
                body = await resp.text()
                raise RuntimeError(
                    f"Monthly data request failed: HTTP {resp.status}: {body[:500]}"
                )
            payload = await resp.json()

        inner = payload.get("Data", {}).get("Data")
        if not inner:
            raise RuntimeError(f"Monthly response has no Data.Data: {payload!r}")
        chart = json.loads(inner) if isinstance(inner, str) else inner

        series = chart.get("series", {}) or {}
        usage_points = (series.get("usage") or {}).get("data") or []
        cost_points = (series.get("cost") or {}).get("data") or []
        if not usage_points:
            raise RuntimeError(
                f"Monthly response had no usage series: keys={list(series.keys())}"
            )

        records = []
        for i, u in enumerate(usage_points):
            # The node library uses d.endDate; the python-side field names
            # can vary, so probe a few.
            date_str = u.get("endDate") or u.get("name") or u.get("x")
            if not date_str:
                continue
            parsed = _parse_monthly_date(date_str)
            if parsed is None:
                continue
            cost = None
            if i < len(cost_points):
                cost = cost_points[i].get("y")
            records.append({"date": parsed, "cost": float(cost) if cost else 0.0})
        return records


def _parse_monthly_date(s: str) -> Optional[date]:
    """Parse the various date formats the MPUData endpoint returns."""
    for fmt in (
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%m/%d/%y",
    ):
        try:
            return datetime.strptime(s[: len(fmt) + 4], fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def get_electricity_recent_charges(
    username: str, password: str
) -> DataFrame[RecentCharges]:
    # Uses the same Monthly MPUData endpoint as apearson/southern-company-api's
    # getMonthlyData. Returns one row per historical month with the monthly
    # cost as a "charge" - no HTML parsing, no Selenium.
    #
    # The API dates each record at the first of its month; we shift to day 28
    # so that get_monthly_charges' "bill posted near month boundary" window
    # picks up the previous month's finalized cost.
    records = asyncio.run(_fetch_electricity_monthly_records(username, password))
    processed_rows = []
    for r in records:
        charge_cents = int(round(r["cost"] * 100))
        rec_date = r["date"]
        processed_rows.append(
            {
                "date": rec_date,
                "description": "",
                "charge_cents": charge_cents,
                "payment_cents": 0,
                "balance_cents": 0,
            }
        )
    return RecentCharges.validate(pd.DataFrame(processed_rows))


# Substring that should appear in the From header of RentCafe OTP emails. The
# exact sender varies per property / Yardi deployment, so allow override.
_RENTCAFE_OTP_FROM = os.environ.get("RENTCAFE_OTP_EMAIL_FROM", "rentcafe")


def _try_find(driver: WebDriver, by: str, value: str) -> Optional[WebElement]:
    try:
        return driver.find_element(by, value)
    except NoSuchElementException:
        return None


def _dump_debug_page(driver: WebDriver, label: str) -> None:
    """Save a screenshot + HTML snapshot to /tmp for post-mortem debugging."""
    import tempfile

    tmp = tempfile.gettempdir()
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    base = os.path.join(tmp, f"rentbot-{label}-{stamp}")
    try:
        driver.save_screenshot(base + ".png")
        with open(base + ".html", "w", encoding="utf-8") as f:
            f.write(driver.page_source)
        print(f"Saved debug artifacts to {base}.png and {base}.html")
    except Exception as e:
        print(f"Failed to save debug artifacts: {e}")


def _dashboard_loaded(driver: WebDriver) -> bool:
    return bool(driver.find_elements(By.ID, "tabs")) or bool(
        driver.find_elements(By.ID, "LinkRecentActivity")
    )


def _visible(el: Optional[WebElement]) -> bool:
    return el is not None and el.is_displayed()


def _fill_username_if_needed(driver: WebDriver, email: str) -> None:
    u = _try_find(driver, By.ID, "Username")
    if not _visible(u):
        return
    current = (u.get_attribute("value") or "").strip().lower()
    if current == email.strip().lower():
        return
    try:
        u.clear()
    except Exception:
        pass
    u.send_keys(email)


def _rentcafe_login(driver: WebDriver, email: str) -> None:
    """
    RentCafe's passwordless login has several variants depending on property
    and user state:

      (A) Simple form: #Username + #ContinueBtn
      (B) Three-button picker: Email / Google / Apple (button[onclick*='ShowLoginForm'])
      (C) Full email form with "Send Verification Code" (authenticateUser('OTP',''))
      (D) OTP-delivery-method chooser (#OtpOptionsEmailRadio + #ContinueOTP)
      (E) Six-digit OTP entry (#otpVerification1..6 + #VerifyFTP)
      (F) Dashboard (#tabs / #LinkRecentActivity)

    The site picks whichever it wants for a given session, so we run a state
    machine: look at the current page, advance whichever step is visible,
    repeat until the dashboard loads or we time out.
    """
    otp_start = datetime.now(timezone.utc) - timedelta(seconds=30)
    otp_submitted = False
    deadline = time.time() + HTTP_TIMEOUT_SECONDS * 3
    last_action = None

    def log_step(tag: str) -> None:
        nonlocal last_action
        if tag != last_action:
            print(f"RentCafe login: {tag}")
            last_action = tag

    while time.time() < deadline:
        if _dashboard_loaded(driver):
            log_step("dashboard loaded")
            return

        # (A) Simple email + ContinueBtn form
        continue_btn = _try_find(driver, By.ID, "ContinueBtn")
        if _visible(continue_btn):
            log_step("state A: email + ContinueBtn")
            _fill_username_if_needed(driver, email)
            otp_start = datetime.now(timezone.utc) - timedelta(seconds=30)
            try:
                continue_btn.click()
            except Exception:
                driver.execute_script("arguments[0].click();", continue_btn)
            time.sleep(1.5)
            continue

        # (B) Three-button landing page - pick "Continue with Email"
        email_picker = [
            b
            for b in driver.find_elements(
                By.XPATH, "//button[contains(@onclick, 'ShowLoginForm')]"
            )
            if b.is_displayed()
        ]
        if email_picker:
            log_step("state B: 3-button picker")
            try:
                email_picker[0].click()
            except Exception:
                driver.execute_script("arguments[0].click();", email_picker[0])
            time.sleep(1.0)
            continue

        # (C) "Send Verification Code" page
        send_code = [
            b
            for b in driver.find_elements(
                By.XPATH, "//button[contains(@onclick, \"authenticateUser('OTP'\")]"
            )
            if b.is_displayed()
        ]
        if send_code:
            log_step("state C: send verification code")
            _fill_username_if_needed(driver, email)
            otp_start = datetime.now(timezone.utc) - timedelta(seconds=30)
            try:
                send_code[0].click()
            except Exception:
                driver.execute_script("arguments[0].click();", send_code[0])
            time.sleep(1.5)
            continue

        # (D) OTP-delivery-method chooser
        email_radio = _try_find(driver, By.ID, "OtpOptionsEmailRadio")
        if _visible(email_radio):
            log_step("state D: pick email radio")
            if not email_radio.is_selected():
                try:
                    email_radio.click()
                except Exception:
                    driver.execute_script("arguments[0].click();", email_radio)
            cont_otp = _try_find(driver, By.ID, "ContinueOTP")
            if _visible(cont_otp):
                otp_start = datetime.now(timezone.utc) - timedelta(seconds=30)
                try:
                    cont_otp.click()
                except Exception:
                    driver.execute_script("arguments[0].click();", cont_otp)
                time.sleep(1.5)
            continue

        # (E) Six-digit OTP entry
        otp_first = _try_find(driver, By.ID, "otpVerification1")
        if _visible(otp_first) and not otp_submitted:
            log_step("state E: OTP entry")
            print("Polling Gmail for the RentCafe OTP")
            # Prefer a code that's adjacent to a keyword like "code" or
            # "verification" - the plain `\d{6}` fallback can pick up phone
            # numbers or reference IDs from the email body.
            raw_code = fetch_otp(
                from_contains=_RENTCAFE_OTP_FROM,
                after=otp_start,
                otp_regex=(
                    r"(?is)(?:code|OTP|password|verification|pin|one.?time)"
                    r"[^\d]{0,60}(\d{6})"
                ),
            )
            digits = re.sub(r"\D", "", raw_code)[:6]
            if len(digits) < 6:
                raise RuntimeError(f"Expected 6-digit OTP; got {raw_code!r}")
            print(f"Extracted OTP code {digits[:2]}****; entering it")

            # Clear any previously entered digits, then enter the new one per
            # box. Use JS to also sync the hidden concatenated #otpVerification
            # field in case the page's JS relies on it.
            for i, d in enumerate(digits, start=1):
                field = driver.find_element(By.ID, f"otpVerification{i}")
                try:
                    field.clear()
                except Exception:
                    pass
                field.send_keys(d)

            driver.execute_script(
                "var h=document.getElementById('otpVerification');"
                "if(h){h.value=arguments[0];"
                "h.dispatchEvent(new Event('input',{bubbles:true}));"
                "h.dispatchEvent(new Event('change',{bubbles:true}));}"
                "for(var i=1;i<=6;i++){var e=document.getElementById("
                "'otpVerification'+i);if(e){"
                "e.dispatchEvent(new Event('input',{bubbles:true}));"
                "e.dispatchEvent(new Event('change',{bubbles:true}));}}",
                digits,
            )

            verify = _try_find(driver, By.ID, "VerifyFTP") or _try_find(
                driver, By.ID, "VerifyOTP"
            )
            if verify is None:
                _dump_debug_page(driver, "verify-otp")
                raise RuntimeError("Could not find the Verify-OTP button")
            # The button uses a JS click handler (type='button', no onclick);
            # JS click is more reliable than Selenium's native click.
            driver.execute_script("arguments[0].click();", verify)
            otp_submitted = True
            time.sleep(3.0)
            # If an error message is visible, surface it in the logs for
            # easier debugging on the next retry.
            for err_sel in (
                "#noticeboxdiv_VerifyOTP .msg-error",
                "#noticeboxdiv_VerifyOTP",
                ".error-message",
            ):
                for el in driver.find_elements(By.CSS_SELECTOR, err_sel):
                    if el.is_displayed() and el.text.strip():
                        print(f"RentCafe notice: {el.text.strip()[:200]}")
                        break
            continue

        time.sleep(1.0)

    _dump_debug_page(driver, "login-stuck")
    raise RuntimeError(
        "RentCafe login state machine did not reach the dashboard in time"
    )


def get_apartment_recent_charges(
    username: str, password: str
) -> DataFrame[RecentCharges]:
    # RentCafe is now a passwordless email-OTP flow; the `password` argument is
    # kept for backwards compatibility but is not used.
    del password

    driver = get_driver()
    try:
        driver.get(APARTMENT_LOGIN_PAGE_URL)

        # Dismiss the cookie banner if it's still there (best-effort).
        reject_cookies = _try_find(driver, By.ID, "onetrust-reject-all-handler")
        if reject_cookies and reject_cookies.is_displayed():
            reject_cookies.click()

        _rentcafe_login(driver, username)

        # navigate to recent charge activity table
        recent_activity = driver.find_element(By.ID, "LinkRecentActivity")
        recent_activity.click()

        WebDriverWait(driver, HTTP_TIMEOUT_SECONDS).until(
            EC.presence_of_element_located((By.ID, "PendingActivityDetails"))
        )

        recent_activity_table = driver.find_element(By.ID, "PendingActivityDetails")
        table_html = recent_activity_table.get_attribute("outerHTML")
    finally:
        driver.quit()

    df = pd.read_html(io.StringIO(table_html))[0]

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
