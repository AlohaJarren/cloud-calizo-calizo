# final/server/Dockerfile
#
# Container for the CS 530 final MCP server.
# Build context should be the final/server directory.

FROM python:3.12-slim

# Prevent Python from writing .pyc files and enable unbuffered logs
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies (if needed later for BigQuery, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code into the image
COPY . .

# Create non-root user
RUN useradd -m appuser
USER appuser

# Cloud Run will set PORT; default to 8080 for local testing
ENV PORT=8080

# Entrypoint: run the FastAPI app via uvicorn
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8080"]