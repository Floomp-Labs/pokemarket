import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import HistoryChart, { ChartPoint } from "../components/HistoryChart";
import SourceStrip from "../components/SourceStrip";
import { Stat, fmtPct, pctTone } from "../components/StatChip";
import type { ProductHistory } from "../types";
import { useStore } from "../store";
import { parseTs } from "../util";

const YEAR = 365 * 24 * 3_600_000;

export default function ProductDetail() {
  const { id } = useParams<{ id: string }>();
  const [data, setData] = useState<ProductHistory | null>(null);
  const liveTs = useStore((s) =>
    id ? s.products.find((p) => p.id === id)?.latest_ts : undefined
  );

  useEffect(() => {
    if (!id) return;
    api.productHistory(id, 0).then(setData).catch(console.error);
  }, [id, liveTs]);

  const points: ChartPoint[] = useMemo(
    () =>
      (data?.points ?? [])
        .map((p) => ({
          t: parseTs(p.ts).getTime(),
          market: p.price,
          estimated: p.estimated,
        }))
        .filter((p) => p.market != null)
        .sort((a, b) => a.t - b.t),
    [data]
  );

  const stats = useMemo(() => {
    if (points.length < 2) return null;
    const latest = points[points.length - 1];
    const prev = points[points.length - 2];
    const first = points[0];
    const pct = (ref: ChartPoint) =>
      ref.market ? ((latest.market! - ref.market) / ref.market) * 100 : null;
    const yearAgo = latest.t - YEAR;
    let refYear: ChartPoint | null = null;
    for (const p of points) {
      if (p.t <= yearAgo) refYear = p;
      else break;
    }
    const markets = points.map((p) => p.market!);
    return {
      mom: pct(prev),
      yoy: refYear && refYear !== latest ? pct(refYear) : null,
      all: pct(first),
      high: Math.max(...markets),
      low: Math.min(...markets),
    };
  }, [points]);

  if (!data) return <div className="loading">loading…</div>;
  const p = data.product;
  const alertMarkers = data.alerts.map((a) => ({
    id: a.id,
    t: parseTs(a.ts).getTime(),
    severity: a.severity,
  }));

  return (
    <div className="detail">
      <Link to="/" className="back">
        ← watchlist
      </Link>
      <div className="detail-head">
        {p.image_small && (
          <img className="detail-img product-hero" src={p.image_small} alt={p.name} />
        )}
        <div className="detail-info">
          <h1>{p.name}</h1>
          <div className="muted">{p.set_name ?? "sealed product"}</div>
          <div className="muted">
            tracking {p.price_kind} price ·{" "}
            <a href={p.url} target="_blank" rel="noreferrer" className="ext-link">
              pricecharting ↗
            </a>
          </div>
          <div className="detail-price">
            {p.latest_price != null ? `$${p.latest_price.toFixed(2)}` : "—"}
          </div>
          <SourceStrip sources={data.sources} />
        </div>
      </div>

      {stats && (
        <div className="stats-strip">
          <Stat label="month" value={fmtPct(stats.mom)} tone={pctTone(stats.mom)} />
          <Stat label="1y" value={fmtPct(stats.yoy)} tone={pctTone(stats.yoy)} />
          <Stat label="all-time" value={fmtPct(stats.all)} tone={pctTone(stats.all)} />
          <Stat label="all-time high" value={`$${stats.high.toFixed(2)}`} />
          <Stat label="all-time low" value={`$${stats.low.toFixed(2)}`} />
        </div>
      )}

      <div className="chart-wrap">
        {points.length < 2 ? (
          <p className="empty">
            Not enough history yet — the collector adds a point whenever the price moves.
          </p>
        ) : (
          <HistoryChart points={points} alerts={alertMarkers} />
        )}
      </div>

      {data.alerts.length > 0 && (
        <div className="detail-alerts">
          <h2>Detected anomalies</h2>
          {data.alerts.map((a) => (
            <div key={a.id} className={`alert-item ${a.severity}`}>
              <div className="alert-msg">{a.message}</div>
              <div className="alert-meta">{parseTs(a.ts).toLocaleString()}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
