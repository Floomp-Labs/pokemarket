import type {
  AlertItem,
  CardHistory,
  CardSummary,
  ProductHistory,
  ProductSearchResult,
  ProductSummary,
  SearchResult,
} from "./types";

function json<T>(r: Response): Promise<T> {
  if (!r.ok) throw new Error(`request failed: ${r.status}`);
  return r.json() as Promise<T>;
}

const post = (url: string, body: unknown) =>
  fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

export const api = {
  // cards
  listCards: () => fetch("/api/cards").then((r) => json<CardSummary[]>(r)),
  searchCards: (q: string) =>
    fetch(`/api/cards/search?q=${encodeURIComponent(q)}`).then((r) => json<SearchResult[]>(r)),
  addCard: (id: string) => post("/api/cards", { id }).then((r) => json<{ ok: boolean; id: string }>(r)),
  removeCard: (id: string) =>
    fetch(`/api/cards/${id}`, { method: "DELETE" }).then((r) => json<{ ok: boolean }>(r)),
  history: (id: string, days: number) =>
    fetch(`/api/cards/${id}/history?days=${days}`).then((r) => json<CardHistory>(r)),

  // sealed products
  listProducts: () => fetch("/api/products").then((r) => json<ProductSummary[]>(r)),
  searchProducts: (q: string) =>
    fetch(`/api/products/search?q=${encodeURIComponent(q)}`).then((r) =>
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
    fetch(`/api/products/${id}`, { method: "DELETE" }).then((r) => json<{ ok: boolean }>(r)),
  productHistory: (id: string, days: number) =>
    fetch(`/api/products/${id}/history?days=${days}`).then((r) => json<ProductHistory>(r)),

  // alerts
  alerts: () => fetch("/api/alerts").then((r) => json<AlertItem[]>(r)),
  ackAlert: (id: number) =>
    fetch(`/api/alerts/${id}/ack`, { method: "POST" }).then((r) => json<{ ok: boolean }>(r)),
};
