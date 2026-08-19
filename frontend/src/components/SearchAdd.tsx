import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { ProductSearchResult, SearchResult } from "../types";
import { useStore } from "../store";

type AnyResult = SearchResult | ProductSearchResult;

function isProduct(r: AnyResult): r is ProductSearchResult {
  return "url" in r;
}

export default function SearchAdd({ kind }: { kind: "card" | "product" }) {
  const [q, setQ] = useState("");
  const [results, setResults] = useState<AnyResult[]>([]);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const setCards = useStore((s) => s.setCards);
  const setProducts = useStore((s) => s.setProducts);
  const timer = useRef<number>();

  useEffect(() => {
    if (!q.trim()) {
      setResults([]);
      setOpen(false);
      return;
    }
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => {
      const search = kind === "card" ? api.searchCards : api.searchProducts;
      search(q.trim())
        .then((r) => {
          setResults(r);
          setOpen(true);
        })
        .catch(() => setResults([]));
    }, 300);
    return () => window.clearTimeout(timer.current);
  }, [q, kind]);

  const add = async (r: AnyResult) => {
    setBusy(true);
    try {
      if (isProduct(r)) {
        await api.addProduct(r);
        setProducts(await api.listProducts());
      } else {
        await api.addCard(r.id);
        setCards(await api.listCards());
      }
      setQ("");
      setOpen(false);
    } catch {
      // already tracked or upstream unavailable
    } finally {
      setBusy(false);
    }
  };

  const subtitle = (r: AnyResult) =>
    isProduct(r) ? r.set_name ?? "sealed product" : `${r.set_name} · #${r.number}`;
  const priceLabel = (r: AnyResult) => {
    const price = isProduct(r) ? r.price : r.market;
    return price != null ? `$${price.toFixed(2)}` : null;
  };

  return (
    <div className="add-search">
      <input
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder={
          kind === "card"
            ? "Search cards to track… (e.g. umbreon vmax)"
            : "Search sealed products… (e.g. evolving skies booster box)"
        }
        onFocus={() => results.length > 0 && setOpen(true)}
        onBlur={() => window.setTimeout(() => setOpen(false), 150)}
      />
      {open && results.length > 0 && (
        <div className="search-results">
          {results.map((r) => (
            <div key={r.id} className="search-result" onMouseDown={() => !busy && add(r)}>
              {r.image_small && (
                <img src={r.image_small} alt="" className={isProduct(r) ? "product-img" : ""} />
              )}
              <div className="search-result-text">
                <div>{r.name}</div>
                <div className="muted">
                  {subtitle(r)}
                  {priceLabel(r) ? ` · ${priceLabel(r)}` : ""}
                </div>
              </div>
              <span className="add-plus">+</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
