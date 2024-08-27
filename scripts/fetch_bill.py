"""Fetch the bill amounts for the rent we owe this month from online."""
from dataclasses import dataclass
from datetime import datetime


@dataclass
class RentBill:
    """Payment information due for the current month's rent"""

    rent_amt: float
    utility_amt: float

    @property
    def total_amt(self):
        return self.rent_amt + self.utility_amt


def get_rental_bill_amt(time: datetime, bill_sources: list) -> RentBill:
    """
    Fetch the total rent and utility costs due to be paid.

    The amounts will be for the previous month relative to 'time' (e.g. a time
    in October will return the bill for the September period, which is due in
    October).
    """
    # TODO: Implement this!
    return RentBill(rent_amt=-1, utility_amt=-1)


if __name__ == "__main__":
    bill = get_rental_bill_amt(
        time=datetime.fromisoformat("2023-10-09"),
        bill_sources=[
            # BillWebsite(login_url="https://centennialplaceapartments.securecafe.com/residentservices/centennial-place/userlogin.aspx#tab_PaymentAccounts", bill_url="https://centennialplaceapartments.securecafe.com/residentservices/centennial-place/payments.aspx#tab_RecentActivity")
        ]
    )
    print(
        f"Total owed: ${bill.total_amt:.2f} (${bill.rent_amt:.2f} rent + ${bill.utility_amt:.2f})")
