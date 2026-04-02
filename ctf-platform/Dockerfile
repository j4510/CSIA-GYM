FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# ── System deps ───────────────────────────────────────────────────────────────
# Build deps for nsjail + runtime tools for challenges
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ make git \
    # nsjail build deps
    bison flex libprotobuf-dev protobuf-compiler libnl-route-3-dev \
    pkg-config libcap-dev \
    # challenge runtime
    php-cli socat \
    nodejs npm \
    default-jre \
    # unshare for web challenge sandboxing (part of util-linux, usually present)
    util-linux \
    # misc utils challenge authors might use
    binutils file \
    && npm install -g ts-node typescript \
    && rm -rf /var/lib/apt/lists/*

# ── Build nsjail ──────────────────────────────────────────────────────────────
RUN git clone --depth=1 https://github.com/google/nsjail.git /tmp/nsjail \
    && cd /tmp/nsjail \
    && make -j$(nproc) \
    && cp nsjail /usr/local/bin/nsjail \
    && rm -rf /tmp/nsjail

# ── Unprivileged user for sandboxed challenge processes ───────────────────────
# UID/GID 65534 = nobody — well-known, no home dir, no shell
RUN useradd -u 1500 -M -s /usr/sbin/nologin ctf-sandbox

# ── Python deps ───────────────────────────────────────────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=root:root . .
# Remove secrets that must never be baked into the image
RUN rm -f /app/.env /app/ssl/haucsia.com.key /app/ssl/haucsia.com.pem

RUN mkdir -p /app/instance /app/instance/web_challenges /app/instance/nc_challenges /app/instance/badges /app/instance/avatars \
    && chown -R root:root /app/instance \
    && chmod 755 /app/instance /app/instance/web_challenges /app/instance/nc_challenges /app/instance/badges /app/instance/avatars

EXPOSE 5050

CMD ["gunicorn", "--workers", "1", "--threads", "4", "--bind", "0.0.0.0:5050", \
     "--timeout", "120", "--max-requests", "500", "--max-requests-jitter", "50", "run:app"]
