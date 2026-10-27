import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routers import (auth, masters, docs, documents, returns, admin, inventory, ordering,
                      registers, templates, printing, extraction, audit, statements,
                      employees, expenses, sales_reports)

app = FastAPI(title="Aequm billing API", version="2.4.0",
              description="Multi-tenant invoicing, purchasing and GST returns.")
app.add_middleware(CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173").split(","),
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

<<<<<<< HEAD
for r in (auth, masters, docs, documents, returns, admin, inventory, ordering,
          registers, templates, printing, extraction, audit, statements,
          employees, expenses, sales_reports):
=======
for r in (auth, masters, docs, returns, admin, inventory, ordering,
          registers, templates, printing, extraction, audit, statements, employees, expenses,
          sales_reports):
>>>>>>> fix/report-period-filter
    app.include_router(r.router, prefix="/api")


@app.get("/api/health")
def health():
    return {"status": "ok"}


# v4.4/v4.5 routers; register once without altering existing routes.
from .routers import mailing, signatories

app.include_router(mailing.router, prefix="/api")
app.include_router(signatories.router, prefix="/api")
