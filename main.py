#!/usr/bin/env python3
'''
A quick script to create a GroupMe bot and have it send a reminder message to
our apartment's GroupMe about the rent
'''
from datetime import datetime, timedelta
import os
import re
import typing

import flask
import requests

from sheet import GoogleSheet


TOKEN = os.environ.get('GROUPME_TOKEN')
BOT_ID = os.environ['GROUPME_BOT_ID']
REMINDER_MESSAGE = "It's RENT TIME again for the month!\n\nFill out how long you stayed this past month in the spreadsheet, and pay @Mac Mathis in a few days when your bill is posted: https://docs.google.com/spreadsheets/d/1jwI4B1ZO46nY0fOVBfB21IFQ-HjngvK63HquskJsMJ0/edit#gid=168056278"
HELP_MESSAGE = '''Hey! You can make me do things by typing "/rent <command name>" (without the quotes); here're the available commands:

"/rent show"
    Show how much everyone owes right now + how to pay
"/rent weeks-stayed <num weeks>"
    Mark how long you've stayed this month, e.g. "/rent weeks-stayed 4"
"/rent paid"
    Mark that you've paid this month's rent
"/rent add"
    Add someone new (you, by default) to pay the rent
"/rent remove"
    Removes someone (you, by default) from paying rent
"/rent rent-amt <rent cost>"
    Set the total apartment rent for the month
"/rent utility-amt <rent cost>"
    Set the total apartment utility bill for the month
"/rent help"
    Have this chit-chat with me again, anytime

If you need more info, you can poke around my insides here: https://github.com/JHDeerin/groupmeRentReminder
'''


app = flask.Flask(__name__)
googleSheetConnection = GoogleSheet()


def listGroups(token: str) -> str:
    url = f'https://api.groupme.com/v3/groups?token={token}&per_page=499'
    result = requests.get(url)
    groups = result.json()['response']
    groupInfo = []
    for group in groups:
        groupInfo.append(f'{group["name"]} - {group["id"]}')
    return '\n'.join(groupInfo)


def createBot(
    token: str,
    groupID: str='52458108',
    botName: str='RentBot',
    imageURL: str='https://p.kindpng.com/picc/s/47-476269_cute-clock-png-clip-art-for-kids-clipart.png'):
    botCreationJSON = {
        'bot': {
            'name': botName,
            'group_id': groupID,
            'avatar_url': imageURL
        }
    }
    url = f'https://api.groupme.com/v3/bots?token={token}'
    result = requests.post(url, json=botCreationJSON)
    return result.json()


def sendBotMessage(botID: str, message: str):
    body = {
        'bot_id': botID,
        'text': message
    }
    result = requests.post('https://api.groupme.com/v3/bots/post', json=body)
    return result.text


def is1stDayOfMonth() -> bool:
    time = datetime.utcnow()
    return time.day == 1


def getDefaultTimeForCommand() -> datetime:
    '''
    Returns the default time you should use for the current command (basically
    2 weeks ago, but you should only use the year/month to make decisions)
    '''
    time = datetime.utcnow() - timedelta(days=14)
    return time


class BotCommand():
    def __init__(self):
        self.botTrigger = r'^\s*/rent\s+'
        self.cmdRegex = re.compile(self.botTrigger)

    def isCommand(self, userInput: str):
        return re.search(self.cmdRegex, userInput)

    def execute(self, userInput: str, userName: str=''):
        pass


class HelpCommand(BotCommand):
    def __init__(self):
        super().__init__()
        self.name = 'help'
        self.cmdRegex = re.compile(f'{self.cmdRegex.pattern}help')

    def execute(self, userInput: str, userName: str=''):
        pass
        # sendBotMessage(BOT_ID, HELP_MESSAGE)


class AddCommand(BotCommand):
    def __init__(self):
        super().__init__()
        self.name = 'add'
        self.cmdRegex = re.compile(f'{self.cmdRegex.pattern}add')

    def execute(self, userInput: str, userName: str=''):
        googleSheetConnection.addTenant(userName, getDefaultTimeForCommand())
        sendBotMessage(BOT_ID, f'Added @{userName} to the rent roll')


class RemoveCommand(BotCommand):
    def __init__(self):
        super().__init__()
        self.name = 'remove'
        self.cmdRegex = re.compile(f'{self.cmdRegex.pattern}remove')

    def execute(self, userInput: str, userName: str=''):
        googleSheetConnection.removeTenant(userName, getDefaultTimeForCommand())
        sendBotMessage(BOT_ID, f'Removed @{userName} from the rent roll')


@app.route('/', methods=['POST'])
def parseGroupMeMessage():
    bodyJSON = flask.request.get_json()
    msgText = bodyJSON['text']
    msgUser = bodyJSON['name']

    if not BotCommand().isCommand(msgText):
        return 'Not a Rentbot command', 200

    print(f'Received message "{msgText}"')

    commands = [
        HelpCommand(),
        AddCommand(),
        RemoveCommand()
    ]
    for cmd in commands:
        if cmd.isCommand(msgText):
            print(f'{cmd.name} triggered')
            cmd.execute(msgText, msgUser)
            return 'Parsed message successfully', 200

    sendBotMessage(BOT_ID, "Hmmm, I don't recognize that command (try typing \"/rent help\"?)")
    return f'Unrecognized command "{msgText}"', 400


if __name__ == '__main__':
    if is1stDayOfMonth():
        # TODO: Update this to make sure it only sends the reminder once
        print(sendBotMessage(BOT_ID, REMINDER_MESSAGE))
    app.run(debug=True, port=5000)
