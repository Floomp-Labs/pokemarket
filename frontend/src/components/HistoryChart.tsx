import { useMemo, useState } from "react";
import {
  Area,
  Brush,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceDot,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export interface ChartPoint {
  t: number;
  market: number | null;
  low?: number | null;
  mid?: number | null;
  high?: number | null;
  estimated?: boolean;
}

export interface AlertMarker {
  id: number;
  t: number;
  severity: string;
}

const EXTRAS = [
  { key: "low", color: "#16a34a", name: "Low" },
  { key: "mid", color: "#d97706", name: "Mid" },
  { key: "high", color: "#dc2626", name: "High" },
] as const;

const fmtDate = (t: number) =>
  new Date(t).toLocaleDateString(undefined, { month: "short", day: "numeric" });

function PulseDot(props: { cx?: number; cy?: number }) {
  const { cx, cy } = props;
  if (cx == null || cy == null) return null;
  return (
    <g>
      <circle cx={cx} cy={cy} r={4.5} fill="#2a75bb" />
      <circle cx={cx} cy={cy} r={4.5} className="pulse-ring" />
    </g>
  );
}

function ChartTooltip(props: { active?: boolean; payload?: any[] }) {
  const { active, payload } = props;
  if (!active || !payload?.length) return null;
  const p = payload[0].payload;
  const market = p.market ?? p.market_real ?? p.market_est;
  const row = (label: string, value: number | null | undefined, color?: string) =>
    value != null ? (
      <div className="tip-row" key={label}>
        <span style={color ? { color } : undefined}>{label}</span>
        <span className="tip-val">${value.toFixed(2)}</span>
      </div>
    ) : null;
  return (
    <div className="chart-tip">
      <div className="tip-date">{new Date(p.t).toLocaleString()}</div>
      {row("market", market, "#2a75bb")}
      {row("sma-7", p.sma, "#8b5cf6")}
      {row("low", p.low, "#16a34a")}
      {row("mid", p.mid, "#d97706")}
      {row("high", p.high, "#dc2626")}
      {p.estimated && <div className="tip-est">estimated from Cardmarket trend</div>}
    </div>
  );
}

export default function HistoryChart({
  points,
  alerts,
  withExtras = false,
}: {
  points: ChartPoint[];
  alerts: AlertMarker[];
  withExtras?: boolean;
}) {
  const [visible, setVisible] = useState<Record<string, boolean>>({
    low: false,
    mid: false,
    high: false,
  });
  const [showBand, setShowBand] = useState(true);
  const [showSma, setShowSma] = useState(true);

  // Split market into real vs estimated series so estimated history renders
  // as a dashed amber line; the first real point after an estimated run is
  // duplicated into the est series so the dashed segment connects.
  const data = useMemo(() => {
    const arr = points.map((p, i) => {
      const win = points
        .slice(Math.max(0, i - 6), i + 1)
        .map((q) => q.market)
        .filter((v): v is number => v != null);
      return {
        ...p,
        market_real: p.estimated ? null : p.market,
        market_est: p.estimated ? p.market : null,
        range: p.low != null && p.high != null ? [p.low, p.high] : null,
        sma: win.length ? win.reduce((a, b) => a + b, 0) / win.length : null,
      };
    });
    for (let i = 1; i < arr.length; i++) {
      if (!points[i].estimated && points[i - 1].estimated) {
        arr[i].market_est = arr[i].market_real;
      }
    }
    return arr;
  }, [points]);

  const hasEst = points.some((p) => p.estimated);
  const hasBand = points.some((p) => p.low != null && p.high != null);
  const lastReal = [...data].reverse().find((p) => p.market_real != null);

  const nearestPoint = (t: number): ChartPoint | null => {
    if (points.length === 0) return null;
    return points.reduce((best, p) => (Math.abs(p.t - t) < Math.abs(best.t - t) ? p : best));
  };

  return (
    <div>
      <div className="chart-controls">
        {withExtras &&
          EXTRAS.map((s) => (
            <label key={s.key} style={{ color: s.color }}>
              <input
                type="checkbox"
                checked={visible[s.key]}
                onChange={() => setVisible({ ...visible, [s.key]: !visible[s.key] })}
              />
              {s.name}
            </label>
          ))}
        {hasBand && (
          <label style={{ color: "#94a3b8" }}>
            <input
              type="checkbox"
              checked={showBand}
              onChange={() => setShowBand(!showBand)}
            />
            Low–High band
          </label>
        )}
        <label style={{ color: "#a78bfa" }}>
          <input type="checkbox" checked={showSma} onChange={() => setShowSma(!showSma)} />
          SMA-7
        </label>
      </div>

      <ResponsiveContainer width="100%" height={460}>
        <ComposedChart data={data} margin={{ top: 10, right: 20, bottom: 0, left: 10 }}>
          <defs>
            <linearGradient id="marketFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#2a75bb" stopOpacity={0.22} />
              <stop offset="100%" stopColor="#2a75bb" stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" vertical={false} />
          <XAxis
            dataKey="t"
            type="number"
            domain={["dataMin", "dataMax"]}
            tickFormatter={fmtDate}
            stroke="#64748b"
            tickLine={false}
            axisLine={{ stroke: "#e2e8f0" }}
          />
          <YAxis
            domain={["auto", "auto"]}
            tickFormatter={(v) => `$${v}`}
            stroke="#64748b"
            width={70}
            tickLine={false}
            axisLine={false}
          />
          <Tooltip content={<ChartTooltip />} cursor={{ stroke: "#94a3b8", strokeDasharray: "4 4" }} />
          {showBand && hasBand && (
            <Area
              type="monotone"
              dataKey="range"
              stroke="none"
              fill="#64748b"
              fillOpacity={0.12}
              connectNulls={false}
              isAnimationActive={false}
            />
          )}
          <Area
            type="monotone"
            dataKey="market_real"
            stroke="#2a75bb"
            fill="url(#marketFill)"
            strokeWidth={2.5}
            dot={false}
            connectNulls={false}
            activeDot={{ r: 5, fill: "#2a75bb", stroke: "#ffffff", strokeWidth: 2 }}
          />
          {hasEst && (
            <Line
              type="monotone"
              dataKey="market_est"
              stroke="#d97706"
              strokeDasharray="5 4"
              strokeWidth={2}
              dot={{ r: 3, fill: "#d97706" }}
              connectNulls
              isAnimationActive={false}
            />
          )}
          {showSma && (
            <Line
              type="monotone"
              dataKey="sma"
              stroke="#8b5cf6"
              strokeWidth={1.5}
              strokeDasharray="2 3"
              dot={false}
              connectNulls
              isAnimationActive={false}
            />
          )}
          {withExtras && visible.low && (
            <Line type="monotone" dataKey="low" stroke="#16a34a" dot={false} strokeWidth={1.5} connectNulls />
          )}
          {withExtras && visible.mid && (
            <Line type="monotone" dataKey="mid" stroke="#d97706" dot={false} strokeWidth={1.5} connectNulls />
          )}
          {withExtras && visible.high && (
            <Line type="monotone" dataKey="high" stroke="#dc2626" dot={false} strokeWidth={1.5} connectNulls />
          )}
          {alerts.map((a) => {
            const nearest = nearestPoint(a.t);
            if (!nearest || nearest.market == null) return null;
            return (
              <ReferenceDot
                key={a.id}
                x={nearest.t}
                y={nearest.market}
                r={6}
                fill={a.severity === "critical" ? "#dc2626" : "#d97706"}
                stroke="#ffffff"
                strokeWidth={2}
              />
            );
          })}
          {lastReal && <ReferenceDot x={lastReal.t} y={lastReal.market_real!} shape={<PulseDot />} />}
          {data.length > 12 && (
            <Brush
              dataKey="t"
              height={24}
              stroke="#cbd5e1"
              fill="#f1f5f9"
              tickFormatter={fmtDate}
              travellerWidth={8}
            />
          )}
        </ComposedChart>
      </ResponsiveContainer>
      {hasEst && (
        <div className="est-note">dashed amber = estimated from Cardmarket trend averages</div>
      )}
    </div>
  );
}
