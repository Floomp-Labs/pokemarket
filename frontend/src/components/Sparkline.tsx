import { Line, LineChart, ResponsiveContainer, YAxis } from "recharts";

export default function Sparkline({ data, height = 48 }: { data: number[]; height?: number }) {
  if (data.length < 2) {
    return (
      <div className="spark-empty" style={{ height }}>
        collecting data…
      </div>
    );
  }
  const points = data.map((v, i) => ({ i, v }));
  const up = data[data.length - 1] >= data[0];
  const stroke = up ? "#16a34a" : "#dc2626";
  return (
    <div className="spark" style={{ width: "100%", height }}>
      <ResponsiveContainer>
        <LineChart data={points} margin={{ top: 4, right: 0, bottom: 0, left: 0 }}>
          <YAxis hide domain={["dataMin", "dataMax"]} />
          <Line
            type="monotone"
            dataKey="v"
            dot={false}
            stroke={stroke}
            strokeWidth={2}
            isAnimationActive={false}
            style={{ filter: `drop-shadow(0 0 4px ${stroke}66)` }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
