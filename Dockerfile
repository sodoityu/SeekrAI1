FROM python:3.10-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy dependency files
COPY requirements.txt ./

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY unified_search.py ./
COPY slack_search_standalone.py ./
COPY .mcp.json ./
COPY templates_unified/ ./templates_unified/

# Expose port
EXPOSE 5500

# Set environment variables
ENV FLASK_ENV=production
ENV PYTHONUNBUFFERED=1

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5500/ || exit 1

# Run the application
CMD ["python3", "unified_search.py"]
