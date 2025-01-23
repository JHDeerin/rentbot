FROM python:3.8-slim
COPY --from=ghcr.io/astral-sh/uv:0.5.22 /uv /uvx /bin/

COPY ./pyproject.toml ./
COPY ./uv.lock ./
COPY ./.python-version ./

RUN uv sync --no-dev

COPY ./app /app

ENV GROUPME_TOKEN="<INSERT HERE>"
ENV GROUPME_BOT_ID="<INSERT HERE>"

ENV RENTBOT_GSHEETS_URL="<INSERT HERE>"
ENV RENTBOT_GSHEETS_KEY_PATH="/tmp/gcp_key.json"

CMD ["uv", "run", "gunicorn", "--conf", "app/gunicorn_conf.py", "--bind", "0.0.0.0:80", "app.main:app"]
