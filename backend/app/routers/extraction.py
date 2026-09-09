"""Upload a vendor's invoice as PDF or image and get back a proposed entry.

POST /vendor-invoices/extract   multipart file → proposal JSON
GET  /vendor-invoices/extract/capabilities   what this container can read
"""
import os, shutil
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from ..deps import Ctx, need
from .. import extract as X

router = APIRouter(prefix="/vendor-invoices/extract", tags=["extraction"])
MAX_BYTES = 15 * 1024 * 1024
ALLOWED = (".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp")


@router.get("/capabilities")
def capabilities(ctx: Ctx = Depends(need("vinv"))):
    return {"pdf_text": True,
            "ocr": shutil.which("tesseract") is not None,
            "llm": bool(os.getenv("ANTHROPIC_API_KEY")),
            "max_mb": MAX_BYTES // (1024 * 1024), "types": list(ALLOWED)}


@router.post("")
async def extract(file: UploadFile = File(...), ctx: Ctx = Depends(need("vinv"))):
    name = (file.filename or "upload").lower()
    if not name.endswith(ALLOWED):
        raise HTTPException(422, f"Upload a PDF or an image ({', '.join(ALLOWED)})")
    data = await file.read()
    if len(data) > MAX_BYTES:
        raise HTTPException(413, f"File is larger than {MAX_BYTES // (1024 * 1024)} MB")
    if not data:
        raise HTTPException(422, "The file is empty")
    try:
        text, method = X.read_text(name, data)
    except RuntimeError as e:
        raise HTTPException(422, str(e))
    except Exception as e:
        raise HTTPException(422, f"Could not read that file: {e.__class__.__name__}")
    if len(text.strip()) < 20:
        raise HTTPException(422, "No readable text was found in the file")
    rules = X.parse_rules(text, ctx.tenant.gstin)
    parsed, notes = X.merge(rules, X.parse_llm(text))
    prop = X.match(ctx, parsed)
    prop["warnings"] = notes + prop["warnings"]
    prop["read_method"] = method
    prop["llm_used"] = bool(parsed.get("llm_used"))
    prop["text_preview"] = text[:1500]
    prop["filename"] = file.filename
    return prop
