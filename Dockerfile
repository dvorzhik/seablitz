FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY bot ./bot
COPY static ./static
COPY scripts ./scripts

EXPOSE 8000

# ВАЖНО: один воркер — комнаты матчей хранятся в памяти процесса.
# При масштабировании на несколько инстансов нужно вынести состояние в Redis.
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers", "--forwarded-allow-ips", "*"]
