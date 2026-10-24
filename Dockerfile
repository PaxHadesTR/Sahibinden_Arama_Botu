FROM python:3.12-slim-bookworm

# Avoid prompts from apt
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONPATH=/app
ENV DISPLAY=:99

# Install system dependencies required for Xvfb and Playwright
RUN apt-get update && apt-get install -y --no-install-recommends \
    xvfb \
    curl \
    ca-certificates \
    fonts-liberation \
    procps \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright Chromium and its system dependencies
RUN playwright install --with-deps chromium

# Copy application files
COPY . .

# Ensure data directory exists and entrypoint is executable
RUN mkdir -p /app/data/browser_profile && \
    chmod +x /app/entrypoint.sh

# Persistent volume for SQLite DB and browser session profile
VOLUME ["/app/data"]

ENTRYPOINT ["/app/entrypoint.sh"]
