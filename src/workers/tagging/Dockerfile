FROM python:3.10-slim

WORKDIR /app

# OS deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg libsndfile1 git wget && \
    rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# App code
COPY . /app

ENV TORCH_HOME=/app/.torch

ENTRYPOINT ["python", "tag_stems.py"] 