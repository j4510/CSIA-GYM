FROM python:3.11-slim

WORKDIR /app

# Reduce memory + avoid cache
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y gcc && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/instance && chmod 777 /app/instance

EXPOSE 5050

# 👇 VERY IMPORTANT (low RAM tuning)
CMD ["gunicorn", "--workers", "1", "--threads", "2", "--bind", "0.0.0.0:5050", "--timeout", "60", "run:app"]