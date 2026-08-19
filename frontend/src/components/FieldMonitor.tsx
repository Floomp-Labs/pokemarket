import { useEffect, useState } from "react";

const UNITS = [
  { id: 25, name: "PIKACHU" },
  { id: 6, name: "CHARIZARD" },
  { id: 150, name: "MEWTWO" },
  { id: 94, name: "GENGAR" },
  { id: 197, name: "UMBREON" },
  { id: 149, name: "DRAGONITE" },
];

const art = (id: number) =>
  `https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/other/official-artwork/${id}.png`;

const ROTATE_MS = 8000;

export default function FieldMonitor() {
  const [idx, setIdx] = useState(0);
  const [dead, setDead] = useState<number[]>([]);

  useEffect(() => {
    const t = window.setInterval(() => setIdx((i) => i + 1), ROTATE_MS);
    return () => window.clearInterval(t);
  }, []);

  const units = UNITS.filter((u) => !dead.includes(u.id));
  if (units.length === 0) return null;
  const current = units[idx % units.length];

  return (
    <div className="field-monitor">
      <div className="fm-label">field monitor</div>
      <div className="fm-stage">
        {units.map((u) => (
          <img
            key={u.id}
            src={art(u.id)}
            alt={u.name}
            loading="lazy"
            className={u.id === current.id ? "on" : ""}
            onError={() => setDead((d) => (d.includes(u.id) ? d : [...d, u.id]))}
          />
        ))}
        <div className="fm-scan" />
      </div>
      <div className="fm-caption">
        <span>
          UNIT-{String(current.id).padStart(3, "0")} // {current.name}
        </span>
        <span className="fm-dots">
          {units.map((u, i) => (
            <i key={u.id} className={i === idx % units.length ? "on" : ""} />
          ))}
        </span>
      </div>
    </div>
  );
}
