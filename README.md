# RentBot

![](https://pbs.twimg.com/media/EPYZgsIWsAEZNMs.jpg)

A GroupMe bot that helps calculate the rent (so that ~~Mac~~ I can eat, too).

The bot can receive commands from a text chat (currently GroupMe), and based on that track + display the rents owed by up to 25 people in our apartment (currently via Google Sheets, for human-editable convenience).

## Deployment

Standard GitHub Actions fare: make a push to the `main` branch, and let it deploy to Google Cloud Run. We also trigger a monthly rent reminder via the [GCP Cloud Scheduler](https://console.cloud.google.com/cloudscheduler?hl=en&inv=1&invt=Abnkvw&project=groupme-rentbot) so we can have monthly rent reminders.

The bot needs to be hosted on a server and hooked up to a Google Sheet it can write rents to. Make sure to define the `GROUPME_BOT_ID` environment variable as...well...your [GroupMe bot's](https://dev.groupme.com/tutorials/bots) ID, or the script will totter about like a fop and crash. For the full spreadsheet rent-tracking extravaganza, you'll need to set up [gspread](https://docs.gspread.org/en/latest/oauth2.html#service-account) and set up all the environment variables in `example.env`.

## Development

### Installation

In the repo's root directory, run the following terminal commands:

```bash
uv sync
```

> See here for instructions on [installing uv](https://docs.astral.sh/uv/getting-started/installation/)

### Running Tests

```bash
uv run python -m pytest
```

### Running Server

First, create a `.env` file in the repo root from the `example.env` template. Then run one of the following:

**via Python**
```bash
uv run fastapi run app/main.py --port 5000
```

**via Docker**
```bash
docker compose up
```

You can then send test messages to the app by running `uv run poe test-msg` in another window.

### Applying Linters

```bash
uv run poe lint
```
