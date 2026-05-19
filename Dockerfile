FROM python:3.11-slim-bookworm

LABEL maintainer="ping-667"
LABEL description="QQ群消息监控 — Web版"

# System deps for PaddleOCR
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgfortran5 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps (cache layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY *.py .
COPY static/ static/
COPY templates/ templates/

# Data volume
RUN mkdir -p /data
ENV APPDATA=/data

EXPOSE 5000

ENV QQ_MONITOR_SECRET=""
ENV FLASK_ENV=production

CMD ["python", "app.py"]
