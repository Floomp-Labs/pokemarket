"""Seed the watchlist with iconic cards: python -m app.seed"""

import asyncio
import logging

from sqlmodel import Session

from .db import engine, init_db
from .models import Card
from .service import add_card_from_api
from .tcg_client import TCGClient

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

SEED_CARD_IDS = [
    "base1-4",        # Charizard (Base Set holo)
    "base1-2",        # Blastoise (Base Set holo)
    "base1-15",       # Venusaur (Base Set holo)
    "base1-58",       # Pikachu (Base Set)
    "base1-1",        # Alakazam (Base Set holo)
    "swsh4-25",       # Charizard V (Vivid Voltage)
    "swsh7-215",      # Umbreon VMAX alt art (Evolving Skies)
    "swsh12pt5-20",   # Radiant Charizard (Crown Zenith)
]


async def seed() -> None:
    init_db()
    client = TCGClient()
    try:
        with Session(engine) as session:
            for cid in SEED_CARD_IDS:
                if session.get(Card, cid):
                    log.info("already tracked: %s", cid)
                    continue
                try:
                    card = await add_card_from_api(client, session, cid)
                    log.info("seeded %s (%s)", card.name, card.id)
                except Exception:
                    log.exception("failed to seed %s", cid)
                await asyncio.sleep(0.5)
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(seed())
