#!/usr/bin/env python3
'''
A quick script to create a GroupMe bot and have it send a reminder message to
our apartment's GroupMe about the rent
'''
import os

import requests


TOKEN = os.environ.get('GROUPME_TOKEN')
BOT_ID = os.environ['GROUPME_BOT_ID']
REMINDER_MESSAGE = "It's RENT TIME again for the month!\n\nFill out how long you stayed this past month in the spreadsheet, and pay @Mac Mathis in a few days when your bill is posted: https://docs.google.com/spreadsheets/d/1jwI4B1ZO46nY0fOVBfB21IFQ-HjngvK63HquskJsMJ0/edit#gid=168056278"


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


if __name__ == '__main__':
    print(sendBotMessage(BOT_ID, REMINDER_MESSAGE))
    # print(listGroups(TOKEN))
