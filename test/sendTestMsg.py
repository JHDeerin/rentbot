'''Send a message to the local RentBot server to test if things are working.'''

import requests


def send_test_message(msg: str, user: str = 'Jake Deerin'):
    requests.post('http://localhost:5000/', json={
        'text': msg,
        'name': user
    })


def send_test_reminder():
    requests.get('http://localhost:5000/reminder')


if __name__ == '__main__':
    send_test_message('/rent show')
