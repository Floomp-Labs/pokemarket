import { useState, type MouseEvent } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import AlertsFeed from "../components/AlertsFeed";
import FieldMonitor from "../components/FieldMonitor";
import SearchAdd from "../components/SearchAdd";
import { useStore } from "../store";

function ChangeBadge({ value }: { value: number | null }) {
  if (value == null) return <span className="badge muted">—</span>;
  const cls = value > 0.05 ? "up" : value < -0.05 ? "down" : "flat";
  return (
    <span className={`badge ${cls}`}>
      {value > 0 ? "+" : ""}
      {value.toFixed(1)}%
    </span>
  );
}

export default function Dashboard() {
  const cards = useStore((s) => s.cards);
  const products = useStore((s) => s.products);
  const removeCard = useStore((s) => s.removeCard);
  const removeProduct = useStore((s) => s.removeProduct);
  const [tab, setTab] = useState<"card" | "product">("card");

  const onRemove = (e: MouseEvent, kind: "card" | "product", id: string, name: string) => {
    e.preventDefault();
    e.stopPropagation();
    if (!window.confirm(`Stop tracking ${name}?`)) return;
    const done = kind === "card" ? removeCard : removeProduct;
    (kind === "card" ? api.removeCard(id) : api.removeProduct(id))
      .then(() => done(id))
      .catch(() => window.alert("Could not remove — is the backend running?"));
  };

  const removeBtn = (kind: "card" | "product", id: string, name: string) => (
    <button
      className="tile-remove"
      title="stop tracking"
      aria-label={`stop tracking ${name}`}
      onClick={(e) => onRemove(e, kind, id, name)}
    >
      ×
    </button>
  );

  return (
    <div className="layout">
      <main>
        <div className="toolbar">
          <div className="tabs">
            <button className={tab === "card" ? "active" : ""} onClick={() => setTab("card")}>
              Cards
            </button>
            <button
              className={tab === "product" ? "active" : ""}
              onClick={() => setTab("product")}
            >
              Sealed
            </button>
          </div>
          <SearchAdd kind={tab} key={tab} />
        </div>

        {tab === "card" &&
          (cards.length === 0 ? (
            <p className="empty">No cards tracked yet. Search above to add your first card.</p>
          ) : (
            <div className="card-grid">
              {cards.map((c) => (
                <Link to={`/card/${c.id}`} key={c.id} className="card-tile">
                  {removeBtn("card", c.id, c.name)}
                  <div className="tile-head">
                    {c.image_small && <img src={c.image_small} alt={c.name} loading="lazy" />}
                    <div className="tile-title">
                      <div className="tile-name">{c.name}</div>
                      <div className="tile-set">
                        {c.set_name} · #{c.number}
                      </div>
                      <div className="tile-type">{c.price_type}</div>
                    </div>
                    {c.active_alert && <span className="alert-pip" title="active alert" />}
                  </div>
                  <div className="tile-price">
                    {c.latest_market != null ? `$${c.latest_market.toFixed(2)}` : "no data"}
                  </div>
                  <div className="tile-badges">
                    <ChangeBadge value={c.change_24h} />
                    <span className="badge-label">24h</span>
                    <ChangeBadge value={c.change_7d} />
                    <span className="badge-label">7d</span>
                  </div>
                </Link>
              ))}
            </div>
          ))}

        {tab === "product" &&
          (products.length === 0 ? (
            <p className="empty">
              No sealed products tracked yet. Search above — booster boxes, ETBs, packs.
            </p>
          ) : (
            <div className="card-grid">
              {products.map((p) => (
                <Link to={`/product/${p.id}`} key={p.id} className="card-tile">
                  {removeBtn("product", p.id, p.name)}
                  <div className="tile-head">
                    {p.image_small && (
                      <img src={p.image_small} alt={p.name} loading="lazy" className="product-img" />
                    )}
                    <div className="tile-title">
                      <div className="tile-name">{p.name}</div>
                      <div className="tile-set">{p.set_name}</div>
                      <div className="tile-type">sealed · {p.price_kind}</div>
                    </div>
                    {p.active_alert && <span className="alert-pip" title="active alert" />}
                  </div>
                  <div className="tile-price">
                    {p.latest_price != null ? `$${p.latest_price.toFixed(2)}` : "no data"}
                  </div>
                  <div className="tile-badges">
                    <ChangeBadge value={p.change_24h} />
                    <span className="badge-label">24h</span>
                    <ChangeBadge value={p.change_prev} />
                    <span className="badge-label">MoM</span>
                  </div>
                </Link>
              ))}
            </div>
          ))}
      </main>
      <aside>
        <FieldMonitor />
        <AlertsFeed />
      </aside>
    </div>
  );
}
