import os
from sqlalchemy import create_engine, event
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker, DeclarativeBase

DB_URL = os.getenv("DATABASE_URL",
    "mysql+pymysql://aequm:change-me@localhost:3306/aequm_billing?charset=utf8mb4")
kw = {"pool_pre_ping": True, "future": True}
if DB_URL.startswith("sqlite"):
    kw = {"connect_args": {"check_same_thread": False}, "future": True}
    if DB_URL in ("sqlite://", "sqlite:///:memory:"):
        kw["poolclass"] = StaticPool
engine = create_engine(DB_URL, **kw)

if DB_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _fk(dbapi, _):
        c = dbapi.cursor(); c.execute("PRAGMA foreign_keys=ON"); c.close()

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
class Base(DeclarativeBase): pass

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()
