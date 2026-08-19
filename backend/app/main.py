import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from .collector import collect_all, run_collector
from .config import settings
from .db import init_db
from .pricecharting_client import PriceChartingClient
from .routes import alerts, cards, products
from .tcg_client import TCGClient
from .tcgcsv_client import TCGCSVClient
from .tcgdex_client import TCGdexClient
from .ws import manager

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# Vercel sets VERCEL=1 on every function instance. Serverless invocations
# are short-lived, so the background collector loop must not run there;
# collection is driven by /api/collect (cron) instead.
ON_VERCEL = bool(os.environ.get("VERCEL"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    task = None
    if not ON_VERCEL:
        task = asyncio.create_task(run_collector())
    yield
    if task is not None:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="Pokemon Card Analytics Agent", lifespan=lifespan)

_extra_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", *_extra_origins],
    # Vercel production + preview deployments
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(cards.router)
app.include_router(products.router)
app.include_router(alerts.router)


@app.get("/api/health")
def health():
    return {"ok": True}


@app.api_route("/api/collect", methods=["GET", "POST"])
async def collect_now(authorization: str | None = Header(None)):
    """Run one collection pass. Triggered by Vercel cron (daily) and GitHub
    Actions (every 15 min); both authenticate with a shared bearer token."""
    if settings.collect_token:
        token = (authorization or "").removeprefix("Bearer ").strip()
        if token != settings.collect_token:
            raise HTTPException(401, "invalid collect token")
    elif ON_VERCEL:
        # Never leave an unauthenticated collect endpoint on the public internet.
        raise HTTPException(503, "COLLECT_TOKEN not configured")

    tcg = TCGClient()
    pc = PriceChartingClient()
    csv = TCGCSVClient()
    dex = TCGdexClient()
    try:
        await collect_all(tcg, pc, csv, dex)
    finally:
        await tcg.close()
        await pc.close()
        await csv.close()
        await dex.close()
    return {"ok": True}


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    # WebSockets don't work on Vercel serverless; the frontend falls back
    # to polling. This endpoint serves the self-hosted/local deployment.
    await manager.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(ws)
