from sqlmodel import SQLModel, Session, create_engine

from . import models  # noqa: F401  (register tables on SQLModel.metadata)
from .config import settings

engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})


def _migrate() -> None:
    """Idempotent column additions for databases created by older versions."""
    with engine.begin() as conn:
        snap_cols = {r[1] for r in conn.exec_driver_sql("PRAGMA table_info(pricesnapshot)")}
        for col, ddl in {
            "cm_avg1": "ALTER TABLE pricesnapshot ADD COLUMN cm_avg1 FLOAT",
            "cm_avg7": "ALTER TABLE pricesnapshot ADD COLUMN cm_avg7 FLOAT",
            "cm_avg30": "ALTER TABLE pricesnapshot ADD COLUMN cm_avg30 FLOAT",
            "cm_trend": "ALTER TABLE pricesnapshot ADD COLUMN cm_trend FLOAT",
            "cm_avg_sell": "ALTER TABLE pricesnapshot ADD COLUMN cm_avg_sell FLOAT",
            "cm_low": "ALTER TABLE pricesnapshot ADD COLUMN cm_low FLOAT",
            "variants_json": "ALTER TABLE pricesnapshot ADD COLUMN variants_json TEXT",
            "sources_json": "ALTER TABLE pricesnapshot ADD COLUMN sources_json TEXT",
            "estimated": "ALTER TABLE pricesnapshot ADD COLUMN estimated BOOLEAN DEFAULT 0",
        }.items():
            if col not in snap_cols:
                conn.exec_driver_sql(ddl)

        psnap_cols = {r[1] for r in conn.exec_driver_sql("PRAGMA table_info(productsnapshot)")}
        if "sources_json" not in psnap_cols:
            conn.exec_driver_sql("ALTER TABLE productsnapshot ADD COLUMN sources_json TEXT")

        product_cols = {r[1] for r in conn.exec_driver_sql("PRAGMA table_info(product)")}
        for col, ddl in {
            "tcgcsv_group_id": "ALTER TABLE product ADD COLUMN tcgcsv_group_id INTEGER",
            "tcgcsv_product_id": "ALTER TABLE product ADD COLUMN tcgcsv_product_id INTEGER",
            "tcgcsv_match_attempted": (
                "ALTER TABLE product ADD COLUMN tcgcsv_match_attempted BOOLEAN DEFAULT 0"
            ),
        }.items():
            if col not in product_cols:
                conn.exec_driver_sql(ddl)

        alert_cols = {r[1] for r in conn.exec_driver_sql("PRAGMA table_info(alert)")}
        if "card_id" in alert_cols and "subject_id" not in alert_cols:
            conn.exec_driver_sql("ALTER TABLE alert RENAME COLUMN card_id TO subject_id")
        if "subject_type" not in alert_cols:
            conn.exec_driver_sql("ALTER TABLE alert ADD COLUMN subject_type TEXT DEFAULT 'card'")

        card_cols = {r[1] for r in conn.exec_driver_sql("PRAGMA table_info(card)")}
        for col, ddl in {
            "pc_url": "ALTER TABLE card ADD COLUMN pc_url TEXT",
            "pc_match_attempted": (
                "ALTER TABLE card ADD COLUMN pc_match_attempted BOOLEAN DEFAULT 0"
            ),
            "tcgcsv_group_id": "ALTER TABLE card ADD COLUMN tcgcsv_group_id INTEGER",
            "tcgcsv_product_id": "ALTER TABLE card ADD COLUMN tcgcsv_product_id INTEGER",
            "tcgcsv_match_attempted": (
                "ALTER TABLE card ADD COLUMN tcgcsv_match_attempted BOOLEAN DEFAULT 0"
            ),
            "tcgdex_id": "ALTER TABLE card ADD COLUMN tcgdex_id TEXT",
            "tcgdex_match_attempted": (
                "ALTER TABLE card ADD COLUMN tcgdex_match_attempted BOOLEAN DEFAULT 0"
            ),
        }.items():
            if col not in card_cols:
                conn.exec_driver_sql(ddl)


def init_db() -> None:
    SQLModel.metadata.create_all(engine)
    _migrate()


def get_session():
    with Session(engine) as session:
        yield session
