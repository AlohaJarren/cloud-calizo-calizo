# Dockerfile
# Slim Python base; no cache; non-root; gunicorn entrypoint.

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Work under /app/hw4 so gunicorn can load "app:create_app()"
WORKDIR /app/hw4

# Install deps first for better layer caching
COPY hw4/requirements.txt /app/hw4/requirements.txt
RUN python -m pip install --upgrade pip && pip install -r /app/hw4/requirements.txt

# Copy application code
COPY hw4 /app/hw4

# Bring in HW2 templates and static so the UI renders
COPY hw2/templates /app/hw2/templates
COPY hw2/static /app/hw2/static

# Drop privileges
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

# Cloud Run sets PORT
ENV PORT=8080

# Gunicorn calls the factory function in app.py
CMD gunicorn -w 2 -k gthread -b 0.0.0.0:${PORT} "app:create_app()"
