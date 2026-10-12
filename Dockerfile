FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Basic Pitch (audio -> notes) runs on the onnxruntime already in requirements.txt;
# --no-deps keeps pip from also installing TensorFlow.
RUN pip install --no-cache-dir --no-deps basic-pitch

COPY . .

EXPOSE 8000

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
