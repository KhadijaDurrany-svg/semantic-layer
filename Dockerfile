# Minimal, reproducible, non-root image for the metridef CLI.
FROM python:3.12-slim

# Create an unprivileged user to run as.
RUN useradd --create-home --uid 10001 appuser

WORKDIR /app

# Install dependencies first for better layer caching.
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir . \
    && rm -rf /root/.cache

# Drop privileges.
USER appuser

ENTRYPOINT ["metridef"]
CMD ["bench", "--no-write"]
