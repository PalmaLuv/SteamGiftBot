FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# The bot holds a live session cookie, so it does not run as root. UID 1000 is
# the usual first user on the host, which keeps a mounted config.ini readable.
RUN useradd --uid 1000 --create-home --shell /usr/sbin/nologin app

COPY --chown=app:app . .

# Where config.ini and the state file go when a volume is mounted. Created here,
# owned by the bot, because a new named volume copies the ownership of the
# folder it is mounted over; without it the volume would belong to root and the
# bot could not remember which wins it already announced.
RUN mkdir -p /app/data && chown app:app /app/data

USER app

# Nobody is there to answer the setup questions, so the container reads its
# settings from STEAMGIFTBOT_* variables, from STEAMGIFTBOT_*_FILE secrets, or
# from a mounted config.ini. Add --once to the run command for a single pass:
#   docker run --rm -e STEAMGIFTBOT_COOKIE=... ghcr.io/palmaluv/steamgiftbot --once
# 'docker stop' sends SIGTERM, which the bot turns into a clean stop and summary.
ENTRYPOINT ["python", "main.py", "--no-input"]
