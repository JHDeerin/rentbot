import datetime
from sheet import GoogleSheet, MonthData, MonthlyTenant, MonthNotFoundError
from main import AddCommand, RemoveCommand
import pytest


googleSheetConnection = GoogleSheet()


@pytest.fixture
def unpaidSeptemberNoRentPosted() -> MonthData:
    return MonthData(year=2021, month=9, totalRent=0.0, totalUtility=0.0, tenants={
        'Mac Mathis': MonthlyTenant(name='Mac Mathis', weeksStayed=4.0, isPaid=False),
        'Jake Deerin': MonthlyTenant(name='Jake Deerin', weeksStayed=4.0, isPaid=False),
        'Taylor Daniel': MonthlyTenant(name='Taylor Daniel', weeksStayed=0.0, isPaid=False),
        'Andrew Dallas': MonthlyTenant(name='Andrew Dallas', weeksStayed=0.0, isPaid=False),
        'Andrew Wittenmyer': MonthlyTenant(name='Andrew Wittenmyer', weeksStayed=0.0, isPaid=False),
        'Josh Minter':MonthlyTenant(name='Josh Minter', weeksStayed=4.0, isPaid=False),
        'David Deerin': MonthlyTenant(name='David Deerin', weeksStayed=0.0, isPaid=False),
        'Manny Jonson': MonthlyTenant(name='Manny Jonson', weeksStayed=4.0, isPaid=False)
    })


@pytest.fixture
def partiallyPaidAugustRent() -> MonthData:
    return MonthData(year=2021, month=8, totalRent=1697.0, totalUtility=413.18, tenants={
        'Mac Mathis': MonthlyTenant(name='Mac Mathis', weeksStayed=4.0, isPaid=True),
        'Jake Deerin': MonthlyTenant(name='Jake Deerin', weeksStayed=4.0, isPaid=True),
        'Taylor Daniel': MonthlyTenant(name='Taylor Daniel', weeksStayed=2.0,isPaid=True),
        'Andrew Dallas': MonthlyTenant(name='Andrew Dallas', weeksStayed=4.0, isPaid=True),
        'Andrew Wittenmyer': MonthlyTenant(name='Andrew Wittenmyer', weeksStayed=2.0, isPaid=False),
        'Josh Minter': MonthlyTenant(name='Josh Minter', weeksStayed=4.0, isPaid=True),
        'David Deerin': MonthlyTenant(name='David Deerin', weeksStayed=1.0, isPaid=False),
        'Manny Jonson': MonthlyTenant(name='Manny Jonson', weeksStayed=2.0, isPaid=False)
    })


def testNoTotalRentHasNoCharges(unpaidSeptemberNoRentPosted):
    expected = {'Mac Mathis': 0.0, 'Jake Deerin': 0.0, 'Taylor Daniel': 0.0, 'Andrew Dallas': 0.0, 'Andrew Wittenmyer': 0.0, 'Josh Minter': 0.0, 'David Deerin': 0.0, 'Manny Jonson': 0.0}

    monthAmountsOwed = googleSheetConnection._getAmountsOwedForMonth(unpaidSeptemberNoRentPosted)
    assert monthAmountsOwed == expected


def testPartiallyPaidMonthCharges(partiallyPaidAugustRent):
    expected = {'Andrew Wittenmyer': 183.49391304347824, 'David Deerin': 91.74695652173912, 'Manny Jonson': 183.49391304347824}

    monthAmountsOwed = googleSheetConnection._getAmountsOwedForMonth(partiallyPaidAugustRent)
    assert monthAmountsOwed == expected


def testGettingTenantFromRemovalMsg():
    input = '/rent remove  Andrew Wittenmyer'
    expected = 'Andrew Wittenmyer'

    cmd = RemoveCommand()
    tenant = cmd.getCommandedUser(input)
    assert tenant == expected


def testGettingTenantFromRemovalMsgWithAt():
    input = '/rent remove  @Andrew Wittenmyer'
    expected = 'Andrew Wittenmyer'

    cmd = RemoveCommand()
    tenant = cmd.getCommandedUser(input)
    assert tenant == expected


def testGettingTenantFromRemovalMsgWithoutUser():
    input = '/rent remove '
    expected = ''

    cmd = RemoveCommand()
    tenant = cmd.getCommandedUser(input)
    assert tenant == expected


def testGettingTenantFromAdditionMsg():
    input = '/rent add  Andrew Wittenmyer'
    expected = 'Andrew Wittenmyer'

    cmd = AddCommand()
    tenant = cmd.getCommandedUser(input)
    assert tenant == expected


def testGettingTenantFromAdditionMsgWithAt():
    input = '/rent add  @Andrew Wittenmyer'
    expected = 'Andrew Wittenmyer'

    cmd = AddCommand()
    tenant = cmd.getCommandedUser(input)
    assert tenant == expected


def testGettingTenantFromAdditionMsgWithoutUser():
    input = '/rent add '
    expected = ''

    cmd = AddCommand()
    tenant = cmd.getCommandedUser(input)
    assert tenant == expected


def testLoadingMonthDataWithCommaRent():
    input = [
        ["8/2021"],
        ["Total Rent", "1,697.20"],
        ["Total Utility", "413.18"],
        ["Name", "Weeks Stayed", "Paid?"],
        ["Mac Mathis", "4", "True"]
    ]
    # Prepend with 1 "month" of blank data as header padding
    for i in range(24):
        input.insert(0, [""])

    print(len(input))
    startTimestamp = datetime.datetime(
        googleSheetConnection.START_YEAR,
        googleSheetConnection.START_MONTH,
        1
    )

    monthData = googleSheetConnection._getMonthBlockData(input, startTimestamp)
    assert monthData.totalRent == 1697.20
    assert monthData.totalUtility == 413.18
    assert monthData.year == 2021
    assert monthData.month == 8
    assert len(monthData.tenants) == 1


def testMonthDataExistsReturnsFalseForMissingMonth():
    input = [
        ["8/2021"],
        ["Total Rent", "1,697.20"],
        ["Total Utility", "413.18"],
        ["Name", "Weeks Stayed", "Paid?"],
        ["Mac Mathis", "4", "True"]
    ]
    # Prepend with 1 "month" of blank data as header padding
    for i in range(24):
        input.insert(0, [""])

    testDate = datetime.datetime(9999, 10, 1)
    assert not googleSheetConnection._monthDataExists(
        googleSheetConnection._getAllRows(), testDate
    )


def testTryingToMarkNonExistentMonthAsPaidCausesException():
    testDate = datetime.datetime(9999, 10, 1)
    with pytest.raises(MonthNotFoundError):
        googleSheetConnection.markRentAsPaid("Jake Deerin", testDate)
