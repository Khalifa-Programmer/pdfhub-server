FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    qpdf ghostscript tesseract-ocr tesseract-ocr-eng tesseract-ocr-spa tesseract-ocr-fra tesseract-ocr-deu tesseract-ocr-ara \
    libreoffice-impress fonts-dejavu fonts-liberation \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
COPY public ./public
RUN useradd -m app && chown -R app /app
USER app
ENV PORT=8000
EXPOSE 8000
CMD ["sh","-c","uvicorn app:app --host 0.0.0.0 --port ${PORT}"]
