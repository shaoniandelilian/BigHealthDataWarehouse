FROM node:22-bookworm

# System deps for scrapling/patchright browsers
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip python3-venv \
    curl util-linux procps \
    # patchright/playwright browser deps
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
    libxkbcommon0 libxcomposite1 libxdamage1 libxrandr2 libgbm1 \
    libpango-1.0-0 libcairo2 libasound2 libxshmfence1 libx11-xcb1 \
    && rm -rf /var/lib/apt/lists/*

# Install pi agent globally
RUN npm install -g @mariozechner/pi-coding-agent

# Python deps
RUN pip3 install --no-cache-dir --break-system-packages \
    flask flask-cors openpyxl requests "scrapling[all]" && \
    scrapling install

# App directory
WORKDIR /app

# Copy application code
COPY product-research-app/ ./

# Copy pi agent config
COPY pi-agent/models.json /root/.pi/agent/models.json
COPY pi-agent/settings.json /root/.pi/agent/settings.json

# Copy skills
COPY skills/ /root/.kiro/skills/

# Fix Flask to bind 0.0.0.0
RUN sed -i "s/host='127.0.0.1'/host='0.0.0.0'/" app.py

# Create data dirs
RUN mkdir -p conversations tasks logs

EXPOSE 5001

# Entrypoint: start Flask + cron sidecar loop
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh cron_worker.sh
CMD ["/entrypoint.sh"]
