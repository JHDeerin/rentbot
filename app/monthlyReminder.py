#!/usr/bin/env python3
"""
Triggered by the Heroku scheduler to send monthly reminder messages about rent
to the GroupMe bot
"""

from datetime import datetime

from . import main


def is1stDayOfMonth() -> bool:
    time = datetime.utcnow()
    return time.day == 1


if __name__ == "__main__":
    if is1stDayOfMonth():
        main.remindGroup()
