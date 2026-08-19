import { create } from "zustand";
import type { AlertItem, CardSummary, PriceTick, ProductSummary, ProductTick } from "./types";

interface State {
  cards: CardSummary[];
  products: ProductSummary[];
  alerts: AlertItem[];
  connected: boolean;
  setCards: (cards: CardSummary[]) => void;
  setProducts: (products: ProductSummary[]) => void;
  setAlerts: (alerts: AlertItem[]) => void;
  setConnected: (connected: boolean) => void;
  removeCard: (id: string) => void;
  removeProduct: (id: string) => void;
  applyTick: (tick: PriceTick) => void;
  applyProductTick: (tick: ProductTick) => void;
  applyAlert: (alert: AlertItem) => void;
}

export const useStore = create<State>((set) => ({
  cards: [],
  products: [],
  alerts: [],
  connected: false,
  setCards: (cards) => set({ cards }),
  setProducts: (products) => set({ products }),
  setAlerts: (alerts) => set({ alerts }),
  setConnected: (connected) => set({ connected }),
  removeCard: (id) => set((s) => ({ cards: s.cards.filter((c) => c.id !== id) })),
  removeProduct: (id) => set((s) => ({ products: s.products.filter((p) => p.id !== id) })),
  applyTick: (tick) =>
    set((s) => ({
      cards: s.cards.map((c) =>
        c.id === tick.card_id
          ? {
              ...c,
              latest_market: tick.market,
              latest_ts: tick.ts,
              sparkline:
                tick.market != null ? [...c.sparkline, tick.market].slice(-48) : c.sparkline,
            }
          : c
      ),
    })),
  applyProductTick: (tick) =>
    set((s) => ({
      products: s.products.map((p) =>
        p.id === tick.product_id
          ? {
              ...p,
              latest_price: tick.price,
              latest_ts: tick.ts,
              sparkline: [...p.sparkline, tick.price].slice(-48),
            }
          : p
      ),
    })),
  applyAlert: (alert) =>
    set((s) => ({
      alerts: [alert, ...s.alerts].slice(0, 100),
      cards:
        alert.subject_type === "card"
          ? s.cards.map((c) => (c.id === alert.subject_id ? { ...c, active_alert: true } : c))
          : s.cards,
      products:
        alert.subject_type === "product"
          ? s.products.map((p) => (p.id === alert.subject_id ? { ...p, active_alert: true } : p))
          : s.products,
    })),
}));
