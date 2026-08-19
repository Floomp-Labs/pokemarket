"""Copy all data from the local SQLite file into a hosted Postgres
database (Neon, Supabase, ...). Rows are merged by primary key, so it is
safe to re-run.

    cd backend
    DATABASE_URL=postgres://user:pass@host/db .venv/bin/python -m scripts.migrate_to_postgres
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlmodel import SQLModel, Session, create_engine, select

from app.models import Alert, Card, GradeSnapshot, PriceSnapshot, Product, ProductSnapshot

SQLITE_URL = "sqlite:///./pokemon.db"
TABLES = [Card, PriceSnapshot, GradeSnapshot, Product, ProductSnapshot, Alert]


def normalize(url: str) -> str:
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


def main() -> None:
    target = normalize(os.environ["DATABASE_URL"])
    src = create_engine(SQLITE_URL, connect_args={"check_same_thread": False})
    dst = create_engine(target)
    SQLModel.metadata.create_all(dst)
    with Session(src) as s, Session(dst) as d:
        for model in TABLES:
            rows = s.exec(select(model)).all()
            for row in rows:
                d.merge(model(**row.model_dump()))
            d.commit()
            print(f"{model.__name__}: {len(rows)} rows")


if __name__ == "__main__":
    main()
