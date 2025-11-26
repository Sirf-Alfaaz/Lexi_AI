FROM python:3.11-slim

# Prevent Python from writing .pyc files and buffering stdout
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies required for PyMuPDF + Tesseract OCR
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        g++ \
        tesseract-ocr \
        libtesseract-dev \
        libleptonica-dev \
        libjpeg-dev \
        zlib1g-dev \
        libpng-dev \
        libopenjp2-7-dev \
        libfreetype6-dev \
        libharfbuzz-dev \
        liblcms2-dev \
        libwebp-dev && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000
ENV PORT=8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

