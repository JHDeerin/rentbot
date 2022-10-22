# RentBot

![](https://pbs.twimg.com/media/EPYZgsIWsAEZNMs.jpg)

A GroupMe bot that helps calculate the rent (so that Mac can eat, too).

## Deployment

[Standard Heroku fare](https://devcenter.heroku.com/articles/github-integration): make a push on GitHub, and let it deploy to an instance. We then trigger the script using the [Heroku Scheduler](https://devcenter.heroku.com/articles/scheduler) so we can have monthly rent reminders.

Make sure to define the `GROUPME_BOT_ID` environment variable as...well...your GroupMe bot's ID, or the script will totter about like a fop and crash. For the full spreadsheet rent-tracking extravaganza, you'll need to set up [gspread](https://docs.gspread.org/en/latest/oauth2.html#service-account) and include the following environment variables:

-   The URL to your spreadsheet under `RENTBOT_GSHEETS_URL`
-   The API key to your spreadsheet under `RENTBOT_GSHEETS_KEY`

## Development

### Installation

In the repo's root directory, run the following terminal commands:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

### Running Tests

```bash
python -m pytest
```

### Running Server

First, create a `.env` file in the repo root from the `example.env` template. Then run one of the following:

**via Python**
```bash
gunicorn app.app.main:app -b "0.0.0.0:5000"
```

**via Docker**
```bash
docker compose up
```

You can then send test messages to the app by running `python test/sendTestMsg.py` in another window.

### Applying Linters

```bash
autopep8 --in-place -r .
isort .
flake8 --exclude ".venv"
```
