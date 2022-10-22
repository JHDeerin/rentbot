FROM tiangolo/uwsgi-nginx-flask:python3.8

COPY ./requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY ./app /app

ENV GROUPME_TOKEN="<INSERT HERE>"
ENV GROUPME_BOT_ID="<INSERT HERE>"

ENV RENTBOT_GSHEETS_URL="<INSERT HERE>"
ENV RENTBOT_GSHEETS_KEY_PATH="/tmp/gcp_key.json"

# Base image entrypoint will be used
