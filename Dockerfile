# Root-level Dockerfile for HW4 Cloud Run deploy

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    GUNICORN_CMD_ARGS="--workers=2 --threads=4 --timeout=60"

# Work under /app so hw4 is importable as a package
WORKDIR /app

# Copy HW4 application code and HW2 templates/static
COPY hw4/ /app/hw4/
COPY hw2/templates/ /app/hw2/templates/
COPY hw2/static/ /app/hw2/static/

# Install runtime deps
RUN pip install --no-cache-dir -r /app/hw4/requirements.txt

# Non-root user (Cloud Run friendly)
RUN useradd -m appuser
USER appuser

EXPOSE 8080

# Gunicorn calls the factory function in hw4/app.py
CMD gunicorn -b "0.0.0.0:${PORT:-8080}" "hw4.app:create_app()"
