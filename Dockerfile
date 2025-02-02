FROM --platform=linux/amd64 python:3.8-slim
COPY --from=ghcr.io/astral-sh/uv:0.5.22 /uv /uvx /bin/

# Chrome installation instructions from here: https://stackoverflow.com/a/51266278
# install google chrome
RUN apt-get -y update
RUN apt-get install -y gnupg wget
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add -
RUN sh -c 'echo "deb http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google.list'
RUN apt-get -y update
RUN apt-get install -y google-chrome-stable

# set display port to avoid crash
ENV DISPLAY=:99

COPY ./pyproject.toml ./
COPY ./uv.lock ./
COPY ./.python-version ./

RUN uv sync --no-dev

COPY ./app /app

ENV GROUPME_TOKEN="<INSERT HERE>"
ENV GROUPME_BOT_ID="<INSERT HERE>"

ENV RENTBOT_GSHEETS_URL="<INSERT HERE>"
ENV RENTBOT_GSHEETS_KEY_PATH="/tmp/gcp_key.json"
ENV RENTBOT_START_TIME="2021-08-01"

# Run to install Selenium browser/etc. dependencies
RUN uv run python app/installSeleniumDrivers.py

CMD ["uv", "run", "fastapi", "run", "app/main.py", "--port", "80"]
