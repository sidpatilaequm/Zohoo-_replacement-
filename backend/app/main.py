import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routers import (auth, masters, docs, returns, admin, inventory, ordering,
                      registers, templates, printing, extraction)

app = FastAPI(title="Aequm billing API", version="2.2.0",
              description="Multi-tenant invoicing, purchasing and GST returns.")
app.add_middleware(CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173").split(","),
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

for r in (auth, masters, docs, returns, admin, inventory, ordering,
          registers, templates, printing, extraction):
    app.include_router(r.router, prefix="/api")


@app.get("/api/health")
def health():
    return {"status": "ok"}
