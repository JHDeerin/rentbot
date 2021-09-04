# GroupMe Rent Reminder

![](https://pbs.twimg.com/media/EPYZgsIWsAEZNMs.jpg)

A GroupMe bot that helps calculate the rent the rent (so that Mac can eat, too).

## Deployment

[Standard Heroku fare](https://devcenter.heroku.com/articles/github-integration): make a push on GitHub, and let it deploy to an instance. We then trigger the script using the [Heroku Scheduler](https://devcenter.heroku.com/articles/scheduler) so we can have monthly rent reminders.

Make sure to define the `GROUPME_BOT_ID` environment variable as...well...your GroupMe bot's ID, or the script will totter about like a fop and crash. For the full spreadsheet extravaganza, you'll need to set up [gspread](https://docs.gspread.org/en/latest/oauth2.html#service-account) and include:

-   The URL to your spreadsheet under `RENTBOT_GSHEETS_URL`
-   The API key to your spreadsheet under `RENTBOT_GSHEETS_KEY`
