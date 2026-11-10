"""PDFHub server: the five tools a browser cannot do on its own.

POST /api/{tool}  (multipart/form-data, field "file", plus optional "password" / "lang")
Tools: unlock-pdf, protect-pdf, ocr-pdf, pdf-to-pdfa, powerpoint-to-pdf
Every request runs in its own temporary directory that is deleted afterwards.
"""
import asyncio, os, shutil, subprocess, tempfile
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask

MAX_BYTES = int(os.getenv("MAX_UPLOAD_MB", "50")) * 1024 * 1024
TIMEOUT = int(os.getenv("JOB_TIMEOUT_S", "180"))
LANGS = {"eng", "spa", "fra", "deu", "ara"}          # must match the Dockerfile language packs
slots = asyncio.Semaphore(int(os.getenv("MAX_PARALLEL_JOBS", "2")))
app = FastAPI(title="PDFHub server")


class JobError(Exception):
    pass


def run(cmd, **kw):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT, **kw)
    except subprocess.TimeoutExpired:
        raise JobError("The job took too long and was stopped.")
    return p


def unlock(src, dst, d, password, lang):
    pw = os.path.join(d, "pw"); open(pw, "w").write(password)
    p = run(["qpdf", f"--password-file={pw}", "--decrypt", src, dst])
    if p.returncode == 2 or "invalid password" in p.stderr:
        raise JobError("Wrong password, or the file cannot be decrypted.")
    if p.returncode not in (0, 3):                  # 3 = finished with warnings
        raise JobError("Could not unlock this PDF.")


def protect(src, dst, d, password, lang):
    if len(password) < 4:
        raise JobError("Choose a password of at least 4 characters.")
    args = os.path.join(d, "args")                  # keeps the password out of the process list
    open(args, "w").write("\n".join(["--encrypt", password, password, "256", "--", src, dst]))
    p = run(["qpdf", f"@{args}"])
    if p.returncode not in (0, 3):
        raise JobError("Could not protect this PDF (is it already encrypted?).")


def ocr(src, dst, d, password, lang):
    if lang not in LANGS:
        raise JobError("Unsupported language.")
    p = run(["ocrmypdf", "--skip-text", "--optimize", "1", "-l", lang, src, dst])
    if p.returncode not in (0, 6):                  # 6 = already has text
        raise JobError("OCR failed: " + (p.stderr.strip().splitlines() or ["unknown error"])[-1])
    if p.returncode == 6:
        shutil.copy(src, dst)


def pdfa(src, dst, d, password, lang):
    # ocrmypdf drives Ghostscript with proper PDF/A definitions; a 0 s OCR timeout turns OCR off.
    p = run(["ocrmypdf", "--skip-text", "--output-type", "pdfa-2", "--tesseract-timeout", "0", src, dst])
    if p.returncode not in (0, 6):
        raise JobError("PDF/A conversion failed: " + (p.stderr.strip().splitlines() or ["unknown error"])[-1])
    if p.returncode == 6 and not os.path.exists(dst):
        shutil.copy(src, dst)


def office(src, dst, d, password, lang):
    out = os.path.join(d, "o"); os.makedirs(out)
    profile = "file://" + os.path.join(d, "lo-profile")
    p = run(["soffice", f"-env:UserInstallation={profile}", "--headless", "--norestore",
             "--convert-to", "pdf", "--outdir", out, src])
    res = [f for f in os.listdir(out) if f.endswith(".pdf")]
    if p.returncode != 0 or not res:
        raise JobError("Could not convert this presentation.")
    shutil.move(os.path.join(out, res[0]), dst)


TOOLS = {  # tool -> (function, allowed extensions, output suffix)
    "unlock-pdf": (unlock, (".pdf",), "-unlocked.pdf"),
    "protect-pdf": (protect, (".pdf",), "-protected.pdf"),
    "ocr-pdf": (ocr, (".pdf",), "-ocr.pdf"),
    "pdf-to-pdfa": (pdfa, (".pdf",), "-pdfa.pdf"),
    "powerpoint-to-pdf": (office, (".pptx", ".ppt", ".odp"), ".pdf"),
}


@app.get("/api/health")
def health():
    return {"ok": True, "tools": list(TOOLS)}


@app.post("/api/{tool}")
async def convert(tool: str, file: UploadFile = File(...), password: str = Form(""), lang: str = Form("eng")):
    if tool not in TOOLS:
        raise HTTPException(404, "Unknown tool.")
    fn, exts, suffix = TOOLS[tool]
    name = os.path.basename(file.filename or "file")
    stem, ext = os.path.splitext(name)
    if ext.lower() not in exts:
        raise HTTPException(400, "Unsupported file type. Expected: " + ", ".join(exts))
    d = tempfile.mkdtemp(prefix="pdfhub-")
    cleanup = BackgroundTask(shutil.rmtree, d, True)
    try:
        src, dst = os.path.join(d, "in" + ext.lower()), os.path.join(d, "out.pdf")
        size = 0
        with open(src, "wb") as f:
            while chunk := await file.read(1 << 20):
                size += len(chunk)
                if size > MAX_BYTES:
                    raise HTTPException(413, f"File is larger than {MAX_BYTES >> 20} MB.")
                f.write(chunk)
        async with slots:
            await asyncio.to_thread(fn, src, dst, d, password, lang)
        if not os.path.exists(dst):
            raise JobError("No output was produced.")
        return FileResponse(dst, media_type="application/pdf", filename=stem + suffix, background=cleanup)
    except JobError as e:
        shutil.rmtree(d, ignore_errors=True)
        return JSONResponse({"detail": str(e)}, status_code=422)
    except Exception:
        shutil.rmtree(d, ignore_errors=True)
        raise


app.mount("/", StaticFiles(directory="public", html=True), name="site")
