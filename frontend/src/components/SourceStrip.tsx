import type { SourcePrice } from "../types";

const NAMES: Record<string, string> = {
  pokemontcg: "TCGplayer",
  tcgcsv: "TCGCSV",
  tcgdex: "TCGdex",
  pricecharting: "PriceCharting",
};

export default function SourceStrip({
  sources,
}: {
  sources: Record<string, SourcePrice> | null;
}) {
  if (!sources) return null;
  const entries = Object.entries(sources).filter(([, v]) => v?.market != null);
  if (entries.length === 0) return null;
  return (
    <div className="source-strip">
      <span className="source-label">sources</span>
      {entries.map(([key, v]) => (
        <span key={key} className="source-chip">
          <span className="source-name">{NAMES[key] ?? key}</span>
          <span className="source-price">${v.market!.toFixed(2)}</span>
        </span>
      ))}
    </div>
  );
}
