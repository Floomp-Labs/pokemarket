"""Seed sealed products via PriceCharting search: python -m scripts.seed_products"""

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlmodel import Session

from app.db import engine, init_db
from app.models import Product
from app.pricecharting_client import PriceChartingClient
from app.service import ProductMeta, add_product_from_meta

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

QUERIES = [
    "scarlet and violet booster box",
    "paldea evolved booster box",
    "pokemon 151 elite trainer box",
    "evolving skies booster box",
    "silver tempest booster box",
]


async def seed() -> None:
    init_db()
    client = PriceChartingClient()
    try:
        with Session(engine) as session:
            for q in QUERIES:
                try:
                    results = await client.search_products(q)
                    if not results:
                        log.info("no results for %r", q)
                        continue
                    r = results[0]
                    if session.get(Product, r["id"]):
                        log.info("already tracked: %s", r["name"])
                        continue
                    product = await add_product_from_meta(
                        client, session, ProductMeta(**r)
                    )
                    log.info(
                        "seeded product %s [%s] kind=%s",
                        product.name,
                        product.set_name,
                        product.price_kind,
                    )
                except Exception:
                    log.exception("failed to seed product for %r", q)
                await asyncio.sleep(1.0)
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(seed())
