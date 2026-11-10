# PDFHub server edition

Adds the five tools that need a backend: **Unlock PDF, Protect PDF, OCR PDF, PDF to PDF/A, PowerPoint to PDF**.
The other tools still run in the browser. `public/index.html` is the full site; `app.py` serves it and the API.

## Run with Docker
    docker build -t pdfhub .
    docker run -p 8000:8000 pdfhub
Open http://localhost:8000

## Run without Docker
Install qpdf, ghostscript, tesseract-ocr (plus language packs) and libreoffice-impress, then:
    pip install -r requirements.txt
    uvicorn app:app --port 8000

## API
`POST /api/{tool}` as multipart form data: `file`, plus `password` (unlock, protect) or `lang` (ocr: eng, spa, fra, deu, ara).
Returns the PDF, or JSON `{"detail": "..."}` with status 4xx. `GET /api/health` lists the tools.

## Settings (environment variables)
MAX_UPLOAD_MB (50), JOB_TIMEOUT_S (180), MAX_PARALLEL_JOBS (2).

## Before you put it on the internet
- Serve it over HTTPS; passwords and files travel to the server.
- Add rate limiting and, if needed, login (for example in a reverse proxy). The server has neither.
- Files live only in a per-request temp folder that is deleted after the response.
- The AI tools (Summarizer, Translate) only work inside Claude.ai; elsewhere they show "AI is not available".
- To add more OCR languages, add the tesseract language pack in the Dockerfile and the code in LANGS in app.py.

## Test status
Tested in a sandbox: Protect, Unlock (right and wrong password), PowerPoint to PDF, the OCR endpoint (on a PDF that already had text), static site, temp-folder cleanup.
Not tested: actual OCR of a scanned page and PDF to PDF/A (Ghostscript was not available there), and the browser UI talking to the API.

## Deploy: Render (free, for testing)
1. Push this folder to a GitHub repository.
2. Render Dashboard > New > Blueprint > select the repo > Apply (it reads `render.yaml`).
3. Wait for the Docker build, then open the `onrender.com` URL.
The free plan has 512 MB RAM and 0.1 CPU and sleeps after 15 minutes idle (about 1 minute to wake). Large PowerPoint or OCR jobs may run out of memory there; if so, use the Starter plan.

## Deploy: Fly.io (paid, pay-as-you-go)
    fly auth signup            # a card is required; new accounts have no free tier
    # edit `app` in fly.toml to a unique name
    fly launch --no-deploy --copy-config
    fly deploy
`auto_stop_machines` stops the machine when idle, so cost stays low for light testing.
