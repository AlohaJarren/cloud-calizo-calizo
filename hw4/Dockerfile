# Dockerfile
# Slim Python base; no cache; non-root; gunicorn entrypoint.

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    GUNICORN_CMD_ARGS="--workers=2 --threads=4 --timeout=60"

# Work under /app/hw4 so gunicorn can load "app:create_app()"
WORKDIR /app

# Copy application code and Bring in HW2 templates and static so the UI renders
COPY hw4/ /app/hw4/
COPY hw2/templates/ /app/hw2/templates/
COPY hw2/static/ /app/hw2/static/

# Install runtime deps
RUN pip install --no-cache-dir -r /app/hw4/requirements.txt

# Non-root user (Cloud Run friendly)
RUN useradd -m appuser
USER appuser

# Cloud Run sets PORT
EXPOSE 8080

# Gunicorn calls the factory function in app.py
CMD ["gunicorn", "-b", "0.0.0.0:${PORT}", "hw4.app:create_app()"]