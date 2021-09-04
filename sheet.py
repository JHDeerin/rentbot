from dataclasses import dataclass
from datetime import datetime, timedelta
import os
import typing

import gspread


SHEETS_KEY_PATH = os.environ.get('RENTBOT_GSHEETS_KEY_PATH')
SHEETS_URL = os.environ['RENTBOT_GSHEETS_URL']


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


@dataclass
class CurrentTenant:
    name: str
    monthsUnpaid: typing.List[datetime]


class GoogleSheet():
    '''
    Interacts with the Google Sheet where we store audit info for the rent roll
    (i.e. who's paying rent for each month, how many weeks they
    stayed, total rent cost/utility cost for the month)

    The sheet starts with 25 rows (equal to 1 month block's size) listing the
    current rent payers and the months they owe money for, like this:

    Name,           Months Unpaid...
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
    '''
    def __init__(self):
        self.START_YEAR = 2021
        self.START_MONTH = 8
        self.MAX_USERS = 20
        self.MONTH_BLOCK_SIZE = 25 # allocate 25 rows to each month

        self._connection = gspread.service_account(filename=SHEETS_KEY_PATH)
        self._sheet = self._connection.open_by_url(SHEETS_URL)
        self._wksheet = self._sheet.sheet1

    def _getAllRows(self) -> typing.List[list]:
        return self._wksheet.get_all_values()

    def _getMonthStartRow(self, time: datetime) -> int:
        monthsFromStart = 12 * (time.year - self.START_YEAR) + (time.month - self.START_MONTH)
        # Need the +1 to allow padding for the initial block of users
        return self.MONTH_BLOCK_SIZE * (monthsFromStart + 1)

    def _parseMonthYearString(self, time: str) -> datetime:
        timePieces = time.split('/')
        return datetime(year=int(timePieces[1]), month=int(timePieces[0]), day=1)

    def _getSuccessiveDataRows(self, allRows: typing.List[list], startIndex: int) -> typing.List[list]:
        '''
        Returns all of the successive rows in "allRows" containing data,
        beginning from startIndex (inclusive)
        '''
        dataRows = []
        i = startIndex
        while (i < len(allRows) and allRows[i][0]):
            dataRows.append(allRows[i])
            i += 1
        return dataRows

    def _getMonthBlockData(self, allRows: typing.List[list], time: datetime) -> MonthData:
        '''
        Gets the whole block of data for the given month from the sheet; can
        then parse that data for individual rent payer info
        '''
        startRowIndex = self._getMonthStartRow(time) - 1
        if startRowIndex >= len(allRows):
            return None
        # TODO: Implement this!
        totalRent = float(allRows[startRowIndex + 1][1])
        totalUtility = float(allRows[startRowIndex + 2][1])

        tenants = {}
        tenantRows = self._getSuccessiveDataRows(allRows, startIndex=startRowIndex + 4)
        for name, weeksStayedStr, paidStr in tenantRows:
            tenants[name] = MonthlyTenant(name, float(weeksStayedStr), paidStr.lower() == 'true')

        return MonthData(time.year, time.month, totalRent, totalUtility, tenants)

    def _getCurrentTenantData(self, allRows: typing.List[list]) -> typing.Dict[str, CurrentTenant]:
        '''
        Gets all the current tenants listed at the beginning of the sheet
        '''
        initialTenants = {}
        tenantRows = self._getSuccessiveDataRows(allRows, startIndex=1)
        for row in tenantRows:
            name = row[0]
            monthsUnpaid = []
            timeStrings = str(row[1]).strip().split(',')
            for timeStr in timeStrings:
                monthsUnpaid.append(self._parseMonthYearString(timeStr))
            initialTenants[name] = CurrentTenant(name, monthsUnpaid)
        return initialTenants

    def _monthDataExists(self, allRows: typing.List[list], time: datetime) -> bool:
        startRow = self._getMonthStartRow(time)
        startRowIndex = startRow - 1
        return startRowIndex < len(allRows) and allRows[startRowIndex][0]

    def _updateCurrentTenantsData(self, newData: typing.Dict[str, CurrentTenant]) -> typing.List[dict]:
        '''
        Returns the Google Sheet updates that will update the current tenants
        listed on the top of the sheet to match the given
        '''
        currentTenantsUpdate = {
            'range': 'A2:A2',
            'values': [['']]
        }
        if len(newData) > 0:
            currentTenantsUpdate = {
                'range': f'A2:B{len(newData)+1}',
                'values': [
                    [t.name, ','.join(list(set( [f'{x.month}/{x.year}' for x in t.monthsUnpaid] )))]
                    for t in newData.values()
                ]
            }

        clearRemainingTenantsUpdate = {
            'range': f'A{2+len(newData)}:B{2+self.MAX_USERS}',
            'values': [['', ''] for i in range(self.MAX_USERS - len(newData))]
        }
        return [currentTenantsUpdate, clearRemainingTenantsUpdate]

    def _updateMonthBlockData(self, newData: MonthData) -> typing.List[dict]:
        '''
        Returns the Google Sheet updates that will update the given month's data
        on the sheet to match the given data
        '''
        time = datetime(year=newData.year, month=newData.month, day=1)
        startRow = self._getMonthStartRow(time)

        monthTimeUpdate = {
            'range': f'A{startRow}:A{startRow}',
            'values': [[f'{newData.month}/{newData.year}']]
        }
        costsHeaderUpdate = {
            'range': f'A{startRow+1}:B{startRow+2}',
            'values': [
                ['Total Rent', newData.totalRent],
                ['Total Utility', newData.totalUtility]
            ]
        }
        tenantsHeaderUpdate = {
            'range': f'A{startRow+3}:C{startRow+3}',
            'values': [['Name', 'Weeks Stayed', 'Paid?']]
        }

        monthlyTenantsUpdate = {'range': f'A{startRow+4}:A{startRow+4}', 'values': [['']]}
        if len(newData.tenants) > 0:
            monthlyTenantsUpdate = {
                'range': f'A{startRow+4}:C{startRow+3+len(newData.tenants)}',
                'values': [[t.name, t.weeksStayed, str(t.isPaid)] for t in newData.tenants.values()]
            }

        clearRemainingTenantsUpdate = {
            'range': f'A{startRow+4+len(newData.tenants)}:C{startRow+4+self.MAX_USERS}',
            'values': [['', '', ''] for i in range(self.MAX_USERS - len(newData.tenants))]
        }
        return [monthTimeUpdate, costsHeaderUpdate, tenantsHeaderUpdate, monthlyTenantsUpdate, clearRemainingTenantsUpdate]

    def _createMonthBlockData(self, allRows: typing.List[list], time: datetime) -> typing.List[dict]:
        '''
        Creates the basic, empty block of data for the given month, if it
        doesn't already exist

        Basic algorithm:
        1) Go to the given start row for a month; if it already exists, exit
        2) Get all the users from the initial data
        3) Add the month/year and rent/utility (both as 0.0)
        4) Add all the current users w/ 0 weeks stayed and "unpaid" status
        5) For all the current users, add the current month/year as unpaid to
        the initial data
        '''
        sheetUpdates = []
        if self._monthDataExists(allRows, time):
            return sheetUpdates

        # TODO: Refactor this into separate "updateCurrentTenants"/"updateMonth"
        # functions
        currentTenants = self._getCurrentTenantData(allRows)
        for _, tenant in currentTenants.items():
            tenant.monthsUnpaid.append(time)

        sheetUpdates += self._updateCurrentTenantsData(currentTenants)

        monthData = MonthData(time.year, time.month, totalRent=0, totalUtility=0, tenants={name:MonthlyTenant(name, 0, False) for name in currentTenants})
        sheetUpdates += self._updateMonthBlockData(monthData)

        return sheetUpdates

    def addTenant(self, tenantName: str, time: datetime):
        '''
        Adds the given person to the rent roll (overall and for the current
        month) if they aren't already on it, and if there's enough room

        Basic algorithm:
        1) Check if the user exists in the initial data; if they do, exit
        2) If we're already at the max capacity of users, exit
        3) Add the user to the initial rows
        4) Go to the current month and add them to the next available row w/ 0
        weeks stayed
        '''
        allRows = self._getAllRows()
        currentTenants = self._getCurrentTenantData(allRows)
        if tenantName in currentTenants:
            return

        if len(currentTenants) >= self.MAX_USERS:
            # TODO: Throw some kind of exception instead
            return

        if not self._monthDataExists(allRows, time):
            self._wksheet.batch_update(self._createMonthBlockData(allRows, time))
            allRows = self._getAllRows()
            currentTenants = self._getCurrentTenantData(allRows)

        monthData = self._getMonthBlockData(allRows, time)
        currentTenants[tenantName] = CurrentTenant(tenantName, monthsUnpaid=[time])
        monthData.tenants[tenantName] = (MonthlyTenant(tenantName, 0, False))

        sheetUpdates = []
        sheetUpdates += self._updateCurrentTenantsData(currentTenants)
        sheetUpdates += self._updateMonthBlockData(monthData)
        self._wksheet.batch_update(sheetUpdates)

    def removeTenant(self, tenantName: str, time: datetime):
        '''
        Removes the given person from the rent roll

        Basic algorithm:
        1) Check if the user exists in the initial data; if they don't, exit
        2) If they do, remove them from the initial data at the top
        3) Go to the current month and remove them from there as well
        '''
        allRows = self._getAllRows()
        currentTenants = self._getCurrentTenantData(allRows)
        if tenantName not in currentTenants:
            return

        del currentTenants[tenantName]
        monthData = self._getMonthBlockData(allRows, time)
        if tenantName in monthData.tenants:
            del monthData.tenants[tenantName]

        sheetUpdates = []
        sheetUpdates += self._updateCurrentTenantsData(currentTenants)
        sheetUpdates += self._updateMonthBlockData(monthData)
        self._wksheet.batch_update(sheetUpdates)
