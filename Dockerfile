FROM python:3.13-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN curl -sSL https://install.python-poetry.org | python3 - \
    && ln -s /root/.local/bin/poetry /usr/local/bin/poetry

# Set working directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml poetry.lock ./

# Install Python dependencies
RUN poetry config virtualenvs.create false \
    && poetry install --no-dev --no-interaction --no-ansi

# Copy application files
COPY unified_search.py ./
COPY templates_unified/ ./templates_unified/
COPY ../slack_search_standalone.py ./

# Create directory for credentials
RUN mkdir -p /app/.saved_credentials

# Expose port
EXPOSE 5500

# Set environment variables (can be overridden)
ENV FLASK_ENV=production
ENV PYTHONUNBUFFERED=1

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5500/api/config || exit 1

# Run the application
CMD ["python", "unified_search.py"]
