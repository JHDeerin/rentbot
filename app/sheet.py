import enum
import json
import os
import typing
from dataclasses import dataclass
from datetime import datetime

import gspread

SHEETS_KEY_PATH = os.environ.get("RENTBOT_GSHEETS_KEY_PATH")
SHEETS_KEY = os.environ.get("RENTBOT_GSHEETS_KEY")
SHEETS_URL = os.environ["RENTBOT_GSHEETS_URL"]
RENTBOT_START_TIME = datetime.fromisoformat(os.environ["RENTBOT_START_TIME"])


@dataclass
class MonthlyTenant:
    name: str
    weeksStayed: float
    isPaid: bool


@dataclass
class MonthData:
    year: int
    month: int
    totalRent: float
    totalUtility: float
    tenants: typing.Dict[str, MonthlyTenant]


class StaySchedule(enum.Enum):
    """The type of tenants a given person could be."""

    # Full-time tenants are assumed to stay for the full 4 weeks each month
    FULLTIME = "FULLTIME"

    # Half-time tenants are assumed to stay for 2 weeks each month
    HALFTIME = "HALFTIME"

    # Irregular tenants stay at irregular intervals, and are assumed to have
    # stayed 0 weeks each month unless otherwise noted
    IRREGULAR = "IRREGULAR"


@dataclass
class CurrentTenant:
    name: str
    monthsUnpaid: typing.List[datetime]
    staySchedule: StaySchedule

    def initialWeeksStayed(self) -> float:
        if self.staySchedule == StaySchedule.FULLTIME:
            return 4.0
        elif self.staySchedule == StaySchedule.HALFTIME:
            return 2.0
        return 0.0


class MonthNotFoundError(Exception):
    """Attempted to access a month that doesn't exist in the spreadsheet."""

    pass


class GoogleSheet:
    """
    Interacts with the Google Sheet where we store audit info for the rent roll
    (i.e. who's paying rent for each month, how many weeks they
    stayed, total rent cost/utility cost for the month)

    The sheet starts with 25 rows (equal to 1 month block's size) listing the
    current rent payers and the months they owe money for, like this:

    Name,           Months Unpaid               ...
    Mac Mathis,
    Jake Deerin,    8/2021, 9/2021, 10/2021
    Andrew,         10/2021
    ...

    Starting with August 2021, each month is allocated 25 cells that look like
    this (starting at row 25-48, row 49 blank, then 50-73, 74 blank, etc.):

    <month/year e.g. "8/2021">
    Total Rent,     <rent $ amt>
    Total Utility,  <utility $ amt>
    Name,           Weeks Stayed,   Paid?
    Jake Deerin,    4,              False
    Mac Mathis,     1.5,            True
    ...
    """

    def __init__(self):
        self.START_YEAR = RENTBOT_START_TIME.year
        self.START_MONTH = RENTBOT_START_TIME.month
        self.MAX_USERS = 20
        self.MONTH_BLOCK_SIZE = 25  # allocate 25 rows to each month

        if SHEETS_KEY:
            key = json.loads(SHEETS_KEY)
            self._connection = gspread.service_account_from_dict(key)
            print("Loaded connection from dict")
        else:
            self._connection = gspread.service_account(filename=SHEETS_KEY_PATH)
            print(f"Loaded connection from key path '{SHEETS_KEY_PATH}'")
        self._sheet = self._connection.open_by_url(SHEETS_URL)
        self._wksheet = self._sheet.sheet1

        if self._isEmptySheet():
            print("Empty sheet; initializing...")
            self.initializeNewSheet()
            print("Sheet initialized!")

    def initializeNewSheet(self):
        createCurrentTenantsHeader = {
            "range": "A1:C1",
            "values": [["Name", "Months Unpaid", "Stay Schedule"]],
        }
        sheetUpdates = [createCurrentTenantsHeader]
        self._wksheet.batch_update(sheetUpdates)

    def _isEmptySheet(self) -> bool:
        return len(self._getAllRows()) == 0

    def _getAllRows(self) -> typing.List[list]:
        return self._wksheet.get_all_values()

    def _getMonthStartRow(self, time: datetime) -> int:
        monthsFromStart = 12 * (time.year - self.START_YEAR) + (
            time.month - self.START_MONTH
        )
        # Need the +1 to allow padding for the initial block of users
        return self.MONTH_BLOCK_SIZE * (monthsFromStart + 1)

    def _parseMonthYearString(self, time: str) -> datetime:
        timePieces = time.split("/")
        return datetime(year=int(timePieces[1]), month=int(timePieces[0]), day=1)

    def _getSuccessiveDataRows(
        self, allRows: typing.List[list], startIndex: int
    ) -> typing.List[list]:
        """
        Returns all of the successive rows in "allRows" containing data,
        beginning from startIndex (inclusive)
        """
        dataRows = []
        i = startIndex
        while i < len(allRows) and allRows[i][0]:
            dataRows.append(allRows[i])
            i += 1
        return dataRows

    def _monthDataExists(self, allRows: typing.List[list], time: datetime) -> bool:
        startRow = self._getMonthStartRow(time)
        startRowIndex = startRow - 1
        return startRowIndex < len(allRows) and allRows[startRowIndex][0]

    @classmethod
    def _toBool(cls, cellValue: str) -> bool:
        return cellValue.lower() == "true"

    @classmethod
    def _toFloat(cls, cellValue: str) -> float:
        return float(cellValue.replace(",", ""))

    @classmethod
    def _getTenantsFromMonthRows(
        cls, tenantRows: typing.List[typing.List[str]]
    ) -> typing.Dict[str, MonthlyTenant]:
        """Get the tenants from a given month's data rows."""
        tenants = {}
        for name, weeksStayedStr, paidStr, *_unused in tenantRows:
            tenants[name] = MonthlyTenant(
                name, cls._toFloat(weeksStayedStr), cls._toBool(paidStr)
            )
        return tenants

    def _getMonthBlockData(
        self, allRows: typing.List[list], time: datetime
    ) -> MonthData:
        """
        Gets the whole block of data for the given month from the sheet; can
        then parse that data for individual rent payer info
        """
        if not self._monthDataExists(allRows, time):
            return None

        startRowIndex = self._getMonthStartRow(time) - 1
        totalRent = self._toFloat(allRows[startRowIndex + 1][1])
        totalUtility = self._toFloat(allRows[startRowIndex + 2][1])

        tenants = {}
        tenantRows = self._getSuccessiveDataRows(allRows, startIndex=startRowIndex + 4)
        tenants = self._getTenantsFromMonthRows(tenantRows)

        return MonthData(time.year, time.month, totalRent, totalUtility, tenants)

    def _getCurrentTenant(self, row: typing.List[str]) -> CurrentTenant:
        name = row[0]
        monthsUnpaid = []
        timeStrings = str(row[1]).strip().split(",")
        for timeStr in timeStrings:
            if timeStr:
                monthsUnpaid.append(self._parseMonthYearString(timeStr))
        try:
            staySchedule = StaySchedule(row[2])
        except ValueError:
            staySchedule = StaySchedule.FULLTIME
        return CurrentTenant(name, monthsUnpaid, staySchedule)

    def _getCurrentTenantData(
        self, allRows: typing.List[list]
    ) -> typing.Dict[str, CurrentTenant]:
        """
        Gets all the current tenants listed at the beginning of the sheet
        """
        initialTenants = {}
        tenantRows = self._getSuccessiveDataRows(allRows, startIndex=1)
        for row in tenantRows:
            tenant = self._getCurrentTenant(row)
            initialTenants[tenant.name] = tenant
        return initialTenants

    def _updateCurrentTenantsData(
        self, newData: typing.Dict[str, CurrentTenant]
    ) -> typing.List[dict]:
        """
        Returns the Google Sheet updates that will update the current tenants
        listed on the top of the sheet to match the given
        """
        currentTenantsUpdate = {"range": "A2:A2", "values": [[""]]}
        if len(newData) > 0:
            currentTenantsUpdate = {
                "range": f"A2:C{len(newData) + 1}",
                "values": [
                    [
                        t.name,
                        ",".join(
                            list(set([f"{x.month}/{x.year}" for x in t.monthsUnpaid]))
                        ),
                        t.staySchedule.value,
                    ]
                    for t in newData.values()
                ],
            }

        clearRemainingTenantsUpdate = {
            "range": f"A{2 + len(newData)}:C{2 + self.MAX_USERS}",
            "values": [["", "", ""] for i in range(self.MAX_USERS - len(newData))],
        }
        return [currentTenantsUpdate, clearRemainingTenantsUpdate]

    def _updateMonthBlockData(self, newData: MonthData) -> typing.List[dict]:
        """
        Returns the Google Sheet updates that will update the given month's data
        on the sheet to match the given data
        """
        time = datetime(year=newData.year, month=newData.month, day=1)
        startRow = self._getMonthStartRow(time)

        monthTimeUpdate = {
            "range": f"A{startRow}:A{startRow}",
            "values": [[f"{newData.month}/{newData.year}"]],
        }
        costsHeaderUpdate = {
            "range": f"A{startRow + 1}:B{startRow + 2}",
            "values": [
                ["Total Rent", newData.totalRent],
                ["Total Utility", newData.totalUtility],
            ],
        }
        tenantsHeaderUpdate = {
            "range": f"A{startRow + 3}:C{startRow + 3}",
            "values": [["Name", "Weeks Stayed", "Paid?"]],
        }

        monthlyTenantsUpdate = {
            "range": f"A{startRow + 4}:A{startRow + 4}",
            "values": [[""]],
        }
        if len(newData.tenants) > 0:
            monthlyTenantsUpdate = {
                "range": f"A{startRow + 4}:C{startRow + 3 + len(newData.tenants)}",
                "values": [
                    [t.name, t.weeksStayed, str(t.isPaid)]
                    for t in newData.tenants.values()
                ],
            }

        clearRemainingTenantsUpdate = {
            "range": f"A{startRow + 4 + len(newData.tenants)}:C{startRow + 4 + self.MAX_USERS}",
            "values": [
                ["", "", ""] for i in range(self.MAX_USERS - len(newData.tenants))
            ],
        }
        return [
            monthTimeUpdate,
            costsHeaderUpdate,
            tenantsHeaderUpdate,
            monthlyTenantsUpdate,
            clearRemainingTenantsUpdate,
        ]

    def _createMonthBlockData(
        self, allRows: typing.List[list], time: datetime
    ) -> typing.List[dict]:
        """
        Creates the basic, empty block of data for the given month, if it
        doesn't already exist

        Basic algorithm:
        1) Go to the given start row for a month; if it already exists, exit
        2) Get all the users from the initial data
        3) Add the month/year and rent/utility (both as 0.0)
        4) Add all the current users w/ "unpaid" status and:
            -   0 weeks stayed if they're irregular tenants
            -   4 weeks stayed if they're full-time
        5) For all the current users, add the current month/year as unpaid to
        the initial data
        """
        sheetUpdates = []
        if self._monthDataExists(allRows, time):
            return sheetUpdates

        # TODO: Refactor this into separate "updateCurrentTenants"/"updateMonth"
        # functions
        currentTenants = self._getCurrentTenantData(allRows)
        for _, tenant in currentTenants.items():
            tenant.monthsUnpaid.append(time)

        sheetUpdates += self._updateCurrentTenantsData(currentTenants)

        monthData = MonthData(
            time.year,
            time.month,
            totalRent=0,
            totalUtility=0,
            tenants={
                tenant.name: MonthlyTenant(
                    tenant.name, tenant.initialWeeksStayed(), False
                )
                for tenant in currentTenants.values()
            },
        )
        sheetUpdates += self._updateMonthBlockData(monthData)

        return sheetUpdates

    def addTenant(self, tenantName: str, time: datetime):
        """
        Adds the given person to the rent roll (overall and for the current
        month) if they aren't already on it, and if there's enough room

        Basic algorithm:
        1) Check if the user exists in the initial data; if they do, exit
        2) If we're already at the max capacity of users, exit
        3) Add the user to the initial rows as a FULLTIME tenant
        4) Go to the current month and add them to the next available row w/ 0
        weeks stayed
        """
        allRows = self._getAllRows()
        currentTenants = self._getCurrentTenantData(allRows)
        if tenantName in currentTenants:
            return

        if len(currentTenants) >= self.MAX_USERS:
            # TODO: Throw some kind of exception instead
            return

        monthData = self._getMonthBlockData(allRows, time)
        if not monthData:
            allRows, monthData = self.createNewMonth(time)

        newTenant = CurrentTenant(
            tenantName, monthsUnpaid=[time], staySchedule=StaySchedule.FULLTIME
        )
        currentTenants[tenantName] = newTenant
        monthData.tenants[tenantName] = MonthlyTenant(
            tenantName, newTenant.initialWeeksStayed(), False
        )

        sheetUpdates = []
        sheetUpdates += self._updateCurrentTenantsData(currentTenants)
        sheetUpdates += self._updateMonthBlockData(monthData)
        self._wksheet.batch_update(sheetUpdates)

    def removeTenant(self, tenantName: str, time: datetime):
        """
        Removes the given person from the rent roll

        Basic algorithm:
        1) Check if the user exists in the initial data; if they don't, exit
        2) If they do, remove them from the initial data at the top
        3) Go to the current month and remove them from there as well
        """
        allRows = self._getAllRows()
        currentTenants = self._getCurrentTenantData(allRows)
        if tenantName not in currentTenants:
            return

        del currentTenants[tenantName]
        monthData = self._getMonthBlockData(allRows, time)
        if monthData and tenantName in monthData.tenants:
            del monthData.tenants[tenantName]

        sheetUpdates = []
        sheetUpdates += self._updateCurrentTenantsData(currentTenants)
        if monthData:
            sheetUpdates += self._updateMonthBlockData(monthData)
        self._wksheet.batch_update(sheetUpdates)

    def markRentAsPaid(self, tenantName: str, time: datetime):
        """
        Marks the given person as having paid the rent for the month

        Basic algorithm:
        1) Check if the user exists in the initial data; if they don't, exit
        2) Mark them as having paid for that month (if the month does not exist,
        raise MonthNotFoundError)
        3) Remove the month as being unpaid from the initial data
        """
        allRows = self._getAllRows()
        currentTenants = self._getCurrentTenantData(allRows)
        if tenantName not in currentTenants:
            return

        currentTenants[tenantName].monthsUnpaid = list(
            filter(
                lambda t: t.year != time.year and t.month != time.month,
                currentTenants[tenantName].monthsUnpaid,
            )
        )
        monthData = self._getMonthBlockData(allRows, time)
        print(monthData)
        if monthData is None:
            raise MonthNotFoundError
        if tenantName in monthData.tenants:
            monthData.tenants[tenantName].isPaid = True

        sheetUpdates = []
        sheetUpdates += self._updateCurrentTenantsData(currentTenants)
        sheetUpdates += self._updateMonthBlockData(monthData)
        self._wksheet.batch_update(sheetUpdates)

    def setTotalRent(self, totalRent: float, time: datetime):
        """
        Sets the total rent for the given month

        Basic algorithm:
        1) Check if the month exists in the data; if it doesn't, create it
        2) Update the month data to include the rent amt
        """
        allRows = self._getAllRows()
        monthData = self._getMonthBlockData(allRows, time)
        if not monthData:
            allRows, monthData = self.createNewMonth(time)

        monthData.totalRent = totalRent

        sheetUpdates = []
        sheetUpdates += self._updateMonthBlockData(monthData)
        self._wksheet.batch_update(sheetUpdates)

    def setTotalUtility(self, totalUtility: float, time: datetime):
        """
        Sets the total utility cost for the given month

        Basic algorithm:
        1) Check if the month exists in the data; if it doesn't, create it
        2) Update the month data to include the utility amt
        """
        allRows = self._getAllRows()
        monthData = self._getMonthBlockData(allRows, time)
        if not monthData:
            allRows, monthData = self.createNewMonth(time)

        monthData.totalUtility = totalUtility

        sheetUpdates = []
        sheetUpdates += self._updateMonthBlockData(monthData)
        self._wksheet.batch_update(sheetUpdates)

    def setWeeksStayed(self, weeks: float, tenantName: str, time: datetime):
        """
        Sets the total utility cost for the given month

        Basic algorithm:
        1) Check if the user exists in initial data; if they don't, exit
        2) Check if the given month exists; if it doesn't, create it
        3) Update the month data to include how many weeks they stayed
        """
        allRows = self._getAllRows()
        currentTenants = self._getCurrentTenantData(allRows)
        if tenantName not in currentTenants:
            return

        monthData = self._getMonthBlockData(allRows, time)
        if not monthData:
            allRows, monthData = self.createNewMonth(time)

        monthData.tenants[tenantName].weeksStayed = weeks

        sheetUpdates = []
        sheetUpdates += self._updateMonthBlockData(monthData)
        self._wksheet.batch_update(sheetUpdates)

    def _getAmountsOwedForMonth(self, monthData: MonthData) -> typing.Dict[str, float]:
        totalWeeksStayed = sum(map(lambda x: x.weeksStayed, monthData.tenants.values()))
        # Prevent division by 0 error (totals will still be 0)
        if totalWeeksStayed == 0:
            totalWeeksStayed += 1
        totalCost = monthData.totalRent + monthData.totalUtility

        amountsOwed = {}
        unpaidTenants = list(filter(lambda x: not x.isPaid, monthData.tenants.values()))
        for tenant in unpaidTenants:
            amountsOwed[tenant.name] = totalCost * (
                tenant.weeksStayed / totalWeeksStayed
            )
        return amountsOwed

    def getAmountsOwed(self) -> typing.Dict[str, float]:
        """
        Returns a dictionary of how much all the current tenants owe

        Basic algorithm:
        1) Load all the current tenants; if there are none, return an empty dict
        2) Get all the months that haven't been paid for and load their data
        3) For each of them, calculate how much each person owes and add it to
        the total (if everyone's paid up, this'll be 0.0 for everyone)
        4) Return the totals
        """
        allRows = self._getAllRows()
        currentTenants = self._getCurrentTenantData(allRows)
        if not currentTenants:
            return {}

        monthsOwed = set()
        for tenant in currentTenants.values():
            monthsOwed = monthsOwed.union(set(tenant.monthsUnpaid))

        amountsOwed = {name: 0.0 for name in currentTenants}
        for month in monthsOwed:
            monthData = self._getMonthBlockData(allRows, month)
            monthAmountsOwed = self._getAmountsOwedForMonth(monthData)
            for tenant in amountsOwed:
                if tenant not in monthAmountsOwed:
                    continue
                amountsOwed[tenant] += monthAmountsOwed[tenant]

        return amountsOwed

    def createNewMonth(self, time: datetime) -> typing.Tuple[list, MonthData]:
        """
        Creates the data for the given month, if it doesn't already exist

        Basic algorithm:
        1) Check if the given month exists; if it doesn't, create it
        2) Return the rows and MonthData
        """
        allRows = self._getAllRows()
        self._wksheet.batch_update(self._createMonthBlockData(allRows, time))
        allRows = self._getAllRows()
        return allRows, self._getMonthBlockData(allRows, time)
