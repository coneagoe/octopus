FROM python:3.11-slim

ENV UV_SYSTEM_PYTHON=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    PYTHONUNBUFFERED=1

# git: for git commit/push; other packages are pulled in by playwright --with-deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

# Default git identity for automated commits; override GIT_AUTHOR_* in .env if needed
RUN git config --system user.email "octopus-bot@example.com" \
    && git config --system user.name "Octopus Bot"

RUN pip install --no-cache-dir uv

WORKDIR /app

# Install Python dependencies into system Python
# (source code is volume-mounted at runtime, not baked into the image)
COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --frozen

# Install Playwright Chromium and all required system libraries
RUN playwright install --with-deps chromium

CMD ["bash", "scripts/run.sh"]
