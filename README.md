# GroupMe Rent Reminder

![](https://pbs.twimg.com/media/EPYZgsIWsAEZNMs.jpg)

A simple GroupMe bot that posts monthly reminders for us to pay the rent (so that Mac can eat, too).

## Deployment

[Standard Heroku fare](https://devcenter.heroku.com/articles/github-integration): make a push on GitHub, and let it deploy to an instance. We then trigger the script using the [Heroku Scheduler](https://devcenter.heroku.com/articles/scheduler).

Make sure to define the `GROUPME_BOT_ID` environment variable as...well...your GroupMe bot's ID, or the script will totter about like a fop and crash.
