# docker:cli gives us the Docker CLI binary on Alpine — no repo setup needed
FROM docker:27-cli AS docker-cli

FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Copy Docker CLI binary from the official image
COPY --from=docker-cli /usr/local/bin/docker /usr/local/bin/docker

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

EXPOSE 32526

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "32526", "--workers", "1"]
