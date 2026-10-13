FROM mcr.microsoft.com/playwright/python:v1.57.0-noble
WORKDIR /opt/nexora
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY worker.py .
ENV PYTHONUNBUFFERED=1
ENV NEXORA_PROFILE_DIR=/data/profiles
EXPOSE 8080
CMD ["sh", "-c", "exec gunicorn --workers 1 --threads 8 --timeout 60 --bind 0.0.0.0:${PORT:-8080} worker:app"]
