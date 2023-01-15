FROM python:3.8-slim

COPY ./requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY ./app /app

ENV GROUPME_TOKEN="<INSERT HERE>"
ENV GROUPME_BOT_ID="<INSERT HERE>"

ENV RENTBOT_GSHEETS_URL="<INSERT HERE>"
ENV RENTBOT_GSHEETS_KEY_PATH="/tmp/gcp_key.json"

CMD ["gunicorn", "--conf", "app/gunicorn_conf.py", "--bind", "0.0.0.0:80", "app.main:app"]
