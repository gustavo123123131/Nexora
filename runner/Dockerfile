FROM mcr.microsoft.com/playwright/python:v1.57.0-noble
WORKDIR /opt/nexora
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY worker.py .
ENV PYTHONUNBUFFERED=1
ENV NEXORA_PROFILE_DIR=/data/profiles
EXPOSE 8080
CMD ["python", "worker.py"]
