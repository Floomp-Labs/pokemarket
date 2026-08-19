# PokeMarket Agent

An autonomous analytics agent for Pokemon TCG prices — single cards **and**
sealed products (booster boxes, Elite Trainer Boxes, packs). A Python/FastAPI
agent service continuously polls free sources, stores time-series history in
SQLite, runs anomaly detection on each new data point, and pushes live updates
to a React dashboard over WebSocket — charting every tracked item in real time.

## Data sources

| Subject | Source | History |
| --- | --- | --- |
| Single cards | [pokemontcg.io](https://pokemontcg.io) (TCGPlayer market/low/mid/high, USD) | 7d/30d anchors estimated from Cardmarket trend ratios (`avg7/avg30` vs trend, clamped), flagged `estimated` and drawn dashed; 24h change appears after a day of real polling |
| Single cards, graded | [PriceCharting](https://www.pricecharting.com) Full Price Guide (PSA 1-10 + ungraded, USD) | Each card is auto-matched to its PriceCharting page once; the grade ladder is snapshotted whenever it changes (max once per stale window) |
| Sealed products | [PriceCharting](https://www.pricecharting.com) (scraped search + product pages) | Real monthly history from the embedded `VGPC.chart_data` series, backfilled on add |

## Architecture

```
pokemontcg.io ──> TCGClient ──┐
                              ├─> Collector loop ──> SQLite (snapshots)
PriceCharting ──> PCClient ───┘        │
                                       v
                                 Anomaly detector ──> SQLite (alerts)
                                       │
                                       v
                                 WebSocket hub ──> React dashboard (Recharts)
```

- `backend/app/collector.py` — async loop, polls cards + products every
  `POLL_INTERVAL_SECONDS` (default 15 min), dedupes unchanged prices,
  one-time 30d anchor backfill per card
- `backend/app/agent/detector.py` — pct-change vs previous point, rolling
  z-score vs 30d window, trend-reversal detection, per-subject alert cooldown
- `backend/app/routes/` — REST: card + product watchlist CRUD, search proxies,
  history, alerts
- `frontend/` — Vite + React + TS dashboard: Cards/Sealed tabs, watchlist
  grids with sparklines and 24h/7d badges, per-item charts with alert markers
  and estimated-segment styling, live alerts feed

## Run it

Backend (port 8000):

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m app.seed                  # optional: seed 8 iconic cards
.venv/bin/python -m scripts.seed_products     # optional: seed 5 sealed products
.venv/bin/uvicorn app.main:app --port 8000
```

Frontend (port 5173, proxies `/api` and `/ws` to the backend):

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 — the **Cards** tab tracks singles, the **Sealed**
tab tracks boxes/ETBs/packs. Search (e.g. "mewtwo" or "evolving skies booster
box") and click a result to start tracking it. Charts update live whenever a
new price lands.

## Configuration

Copy `backend/.env.example` to `backend/.env`. Setting `POKEMONTCG_API_KEY`
(free at https://dev.pokemontcg.io/) raises the upstream rate limit.
Thresholds (`ALERT_PCT_THRESHOLD`, `ALERT_Z_THRESHOLD`,
`ALERT_COOLDOWN_MINUTES`) tune the anomaly detector.

## Tests

```bash
cd backend
.venv/bin/python -m pytest tests/
```

## Notes

The free pokemontcg.io feed carries TCGPlayer market/low/mid/high prices that
update roughly daily; the pipeline itself is real-time (poll -> store ->
detect -> push). To get per-sale ticks later, swap a paid feed (tcgfast,
PokeTrace WebSocket, eBay sold listings) into `collector.py` — the detector,
storage, and dashboard are source-agnostic.
