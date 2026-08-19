import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import { CardHistory } from "../types";
import { parseTs } from "../util";
import HistoryChart, { ChartPoint } from "../components/HistoryChart";
import SourceStrip from "../components/SourceStrip";
import { Stat, fmtPct, pctTone } from "../components/StatChip";

const DAY = 24 * 3_600_000;

const PSA_ORDER = ["ungraded", "1", "2", "3", "4", "5", "6", "7", "8", "9", "9.5", "10"];

const fmtMoney = (v: number) =>
  `$${v.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

export default function CardDetail() {
  const { id = "" } = useParams();
  const [data, setData] = useState<CardHistory | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [variant, setVariant] = useState<string | null>(null);

  useEffect(() => {
    api
      .history(id, 400)
      .then(setData)
      .catch((e: Error) => setErr(e.message));
  }, [id]);

  const pv = variant ?? data?.card.price_type ?? null;

  // For the selected variant: use its block from the per-snapshot variants
  // payload; fall back to top-level fields when it is the tracked variant.
  const points: ChartPoint[] = useMemo(() => {
    if (!data) return [];
    const isPrimary = pv === data.card.price_type;
    return data.points
      .map((p) => {
        const v = pv ? p.variants?.[pv] : null;
        return {
          t: parseTs(p.ts).getTime(),
          market: v?.market ?? (isPrimary ? p.market : null),
          low: v?.low ?? (isPrimary ? p.low : null),
          mid: v?.mid ?? (isPrimary ? p.mid : null),
          high: v?.high ?? (isPrimary ? p.high : null),
          estimated: p.estimated,
        };
      })
      .filter((p) => p.market != null)
      .sort((a, b) => a.t - b.t);
  }, [data, pv]);

  const variants = useMemo(() => {
    const keys = new Set<string>();
    (data?.points ?? []).forEach((p) => {
      if (p.variants) Object.keys(p.variants).forEach((k) => keys.add(k));
    });
    return [...keys];
  }, [data]);

  const stats = useMemo(() => {
    if (!points.length) return null;
    const now = Date.now();
    const latest = points[points.length - 1];
    const refAt = (back: number, tol: number) => {
      const target = now - back;
      let best: ChartPoint | null = null;
      for (const p of points) {
        if (p.t <= target) best = p;
        else break;
      }
      return best && best.t >= target - tol ? best : null;
    };
    const pct = (ref: ChartPoint | null) =>
      ref?.market ? ((latest.market! - ref.market) / ref.market) * 100 : null;
    const markets = points.map((p) => p.market!);
    const returns = markets.slice(1).map((m, i) => (m - markets[i]) / markets[i]);
    const mean = returns.reduce((a, b) => a + b, 0) / (returns.length || 1);
    const vol =
      returns.length > 1
        ? Math.sqrt(
            returns.reduce((a, r) => a + (r - mean) ** 2, 0) / (returns.length - 1)
          ) * 100
        : null;
    const spread =
      latest.low != null && latest.high != null && latest.market
        ? ((latest.high - latest.low) / latest.market) * 100
        : null;
    return {
      c24: pct(refAt(DAY, DAY)),
      c7: pct(refAt(7 * DAY, 2 * DAY)),
      c30: pct(refAt(30 * DAY, 3 * DAY)),
      high: Math.max(...markets),
      low: Math.min(...markets),
      vol,
      spread,
    };
  }, [points]);

  // Same shape the sealed detail chart gets: market line only, no band/extras.
  const chartPoints: ChartPoint[] = points.map((p) => ({
    t: p.t,
    market: p.market,
    estimated: p.estimated,
  }));

  if (err) return <div className="panel">Failed to load: {err}</div>;
  if (!data) return <div className="panel">Loading…</div>;

  const { card, alerts, psa } = data;

  return (
    <div className="detail">
      <Link to="/" className="back">
        ← back
      </Link>
      <div className="detail-head">
        <img src={card.image_small ?? undefined} alt={card.name} />
        <div>
          <h2>{card.name}</h2>
          <div className="muted">
            {card.set_name} · {card.rarity}
          </div>
          <div className="price-line">
            <span className="price">
              {card.latest_market != null ? `$${card.latest_market.toFixed(2)}` : "—"}
            </span>
            <span className="muted">{card.price_type} market · compiled</span>
          </div>
          <SourceStrip sources={data.sources} />
        </div>
      </div>

      {stats && (
        <div className="stats-strip">
          <Stat label="24h" value={fmtPct(stats.c24)} tone={pctTone(stats.c24)} />
          <Stat label="7d" value={fmtPct(stats.c7)} tone={pctTone(stats.c7)} />
          <Stat label="30d" value={fmtPct(stats.c30)} tone={pctTone(stats.c30)} />
          <Stat label="range high" value={`$${stats.high.toFixed(2)}`} />
          <Stat label="range low" value={`$${stats.low.toFixed(2)}`} />
          <Stat label="volatility" value={stats.vol != null ? `${stats.vol.toFixed(1)}%` : "—"} />
          <Stat label="low–high spread" value={stats.spread != null ? `${stats.spread.toFixed(1)}%` : "—"} />
        </div>
      )}

      {psa && (
        <div className="psa-panel">
          <div className="psa-head">
            <h3>PSA price guide</h3>
            {psa.url && (
              <a href={psa.url} target="_blank" rel="noreferrer" className="ext-link">
                pricecharting ↗
              </a>
            )}
            <span className="muted">updated {parseTs(psa.ts).toLocaleString()}</span>
          </div>
          <div className="stats-strip">
            {PSA_ORDER.filter((g) => psa.prices[g] != null).map((g) => (
              <div key={g} className={`stat-chip psa-chip${g === "10" ? " hot" : ""}`}>
                <div className="stat-label">{g === "ungraded" ? "Raw" : `PSA ${g}`}</div>
                <div className="stat-value">{fmtMoney(psa.prices[g])}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {variants.length > 1 && (
        <div className="variant-picker">
          {variants.map((v) => (
            <button
              key={v}
              className={`variant-btn ${pv === v ? "active" : ""}`}
              onClick={() => setVariant(v)}
            >
              {v}
            </button>
          ))}
        </div>
      )}

      <div className="chart-wrap">
        {chartPoints.length < 2 ? (
          <p className="empty">
            Not enough history yet — the collector adds a point whenever the price moves.
          </p>
        ) : (
          <HistoryChart
            points={chartPoints}
            alerts={alerts.map((a) => ({ id: a.id, t: parseTs(a.ts).getTime(), severity: a.severity }))}
          />
        )}
      </div>
    </div>
  );
}
