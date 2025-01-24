"""Send a message to the local RentBot server to test if things are working."""

import argparse

import requests


def send_test_message(msg: str, user: str = "Jake Deerin"):
    requests.post("http://localhost:5000/", json={"text": msg, "name": user})


def send_test_reminder():
    requests.get("http://localhost:5000/reminder")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "msg", type=str, help="message to send to rentbot, e.g. '/rent help'"
    )
    parser.add_argument(
        "--reminder",
        action="store_true",
        help="whether to trigger the 'reminder' action for rentbot",
    )
    args = parser.parse_args()
    if args.reminder:
        send_test_reminder()
        return
    send_test_message(args.msg)


if __name__ == "__main__":
    main()
