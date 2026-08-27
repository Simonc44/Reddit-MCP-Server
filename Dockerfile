FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

# Install the Playwright driver + Chromium with its system dependencies,
# then the project's Python dependencies. All in one layer for a smaller image.
COPY requirements.txt .
RUN pip install --no-cache-dir playwright && \
    playwright install --with-deps chromium && \
    pip install --no-cache-dir -r requirements.txt && \
    rm -rf /root/.cache /var/lib/apt/lists/*

COPY server.py .

# Run as an unprivileged user. Chromium needs write access to its browser
# directory (/ms-playwright) and the app needs its working directory.
RUN useradd --create-home --shell /usr/sbin/nologin reddit && \
    chown -R reddit:reddit /app /ms-playwright

USER reddit

# The server speaks MCP over stdio:
#   docker build -t reddit-mcp-server .
#   docker run -i --rm reddit-mcp-server
CMD ["python", "server.py"]
