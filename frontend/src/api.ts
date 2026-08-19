import type {
  AlertItem,
  CardHistory,
  CardSummary,
  ProductHistory,
  ProductSearchResult,
  ProductSummary,
  SearchResult,
} from "./types";

// Same-origin in dev (Vite proxies /api to localhost:8000). In production,
// set VITE_API_URL to the hosted backend, e.g. https://pokemarket-api.fly.dev
const BASE = (import.meta.env.VITE_API_URL ?? "").replace(/\/$/, "");

function json<T>(r: Response): Promise<T> {
  if (!r.ok) throw new Error(`request failed: ${r.status}`);
  return r.json() as Promise<T>;
}

const post = (url: string, body: unknown) =>
  fetch(BASE + url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

export const api = {
  // cards
  listCards: () => fetch(`${BASE}/api/cards`).then((r) => json<CardSummary[]>(r)),
  searchCards: (q: string) =>
    fetch(`${BASE}/api/cards/search?q=${encodeURIComponent(q)}`).then((r) =>
      json<SearchResult[]>(r)
    ),
  addCard: (id: string) =>
    post("/api/cards", { id }).then((r) => json<{ ok: boolean; id: string }>(r)),
  removeCard: (id: string) =>
    fetch(`${BASE}/api/cards/${id}`, { method: "DELETE" }).then((r) =>
      json<{ ok: boolean }>(r)
    ),
  history: (id: string, days: number) =>
    fetch(`${BASE}/api/cards/${id}/history?days=${days}`).then((r) => json<CardHistory>(r)),

  // sealed products
  listProducts: () => fetch(`${BASE}/api/products`).then((r) => json<ProductSummary[]>(r)),
  searchProducts: (q: string) =>
    fetch(`${BASE}/api/products/search?q=${encodeURIComponent(q)}`).then((r) =>
      json<ProductSearchResult[]>(r)
    ),
  addProduct: (p: ProductSearchResult) =>
    post("/api/products", {
      id: p.id,
      name: p.name,
      set_name: p.set_name,
      url: p.url,
      image_small: p.image_small,
      used: p.used,
      cib: p.cib,
      new: p.new,
    }).then((r) => json<{ ok: boolean; id: string }>(r)),
  removeProduct: (id: string) =>
    fetch(`${BASE}/api/products/${id}`, { method: "DELETE" }).then((r) =>
      json<{ ok: boolean }>(r)
    ),
  productHistory: (id: string, days: number) =>
    fetch(`${BASE}/api/products/${id}/history?days=${days}`).then((r) =>
      json<ProductHistory>(r)
    ),

  // alerts
  alerts: () => fetch(`${BASE}/api/alerts`).then((r) => json<AlertItem[]>(r)),
  ackAlert: (id: number) =>
    post(`${BASE}/api/alerts/${id}/ack`, {}).then((r) => json<{ ok: boolean }>(r)),
};
