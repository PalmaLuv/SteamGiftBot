FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Nobody is there to answer the setup questions, so the container reads its
# settings from STEAMGIFTBOT_* variables or from a mounted config.ini.
# Add --once to the run command for a single pass:
#   docker run --rm -e STEAMGIFTBOT_COOKIE=... ghcr.io/palmaluv/steamgiftbot --once
ENTRYPOINT ["python", "main.py", "--no-input"]
