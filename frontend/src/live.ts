import { useEffect } from "react";
import { api } from "./api";
import { useStore } from "./store";

// Dev: same-origin /ws (Vite proxies to the backend). Production: derive
// from VITE_API_URL (https://api.example.com -> wss://api.example.com/ws).
const API_BASE = (import.meta.env.VITE_API_URL ?? "").replace(/\/$/, "");
const WS_URL = API_BASE
  ? `${API_BASE.replace(/^http/, "ws")}/ws`
  : `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`;

const POLL_MS = 60_000;
// Serverless hosts (Vercel) can't hold WebSockets; after a few failed
// attempts we stop retrying and poll the REST API instead.
const MAX_WS_RETRIES = 3;

export function useLiveSocket() {
  const applyTick = useStore((s) => s.applyTick);
  const applyProductTick = useStore((s) => s.applyProductTick);
  const applyAlert = useStore((s) => s.applyAlert);
  const setConnected = useStore((s) => s.setConnected);
  const setCards = useStore((s) => s.setCards);
  const setProducts = useStore((s) => s.setProducts);
  const setAlerts = useStore((s) => s.setAlerts);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let closed = false;
    let retries = 0;
    let polling = false;
    let timer: number | undefined;
    let pollTimer: number | undefined;

    const poll = async () => {
      try {
        const [cards, products, alerts] = await Promise.all([
          api.listCards(),
          api.listProducts(),
          api.alerts(),
        ]);
        setCards(cards);
        setProducts(products);
        setAlerts(alerts);
        setConnected(true);
      } catch {
        setConnected(false);
      }
    };

    const startPolling = () => {
      if (polling) return;
      polling = true;
      poll();
      pollTimer = window.setInterval(poll, POLL_MS);
    };

    const connect = () => {
      if (polling) return;
      try {
        ws = new WebSocket(WS_URL);
      } catch {
        startPolling();
        return;
      }
      ws.onopen = () => {
        retries = 0;
        setConnected(true);
      };
      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data);
          if (msg.type === "price_tick") applyTick(msg);
          else if (msg.type === "product_tick") applyProductTick(msg);
          else if (msg.type === "alert") applyAlert(msg.alert);
        } catch (e) {
          console.error("bad ws message", e);
        }
      };
      ws.onclose = () => {
        setConnected(false);
        if (closed || polling) return;
        if (++retries > MAX_WS_RETRIES) {
          startPolling();
          return;
        }
        const delay = Math.min(10_000, 500 * 2 ** retries);
        timer = window.setTimeout(connect, delay);
      };
    };
    connect();

    return () => {
      closed = true;
      window.clearTimeout(timer);
      window.clearInterval(pollTimer);
      ws?.close();
    };
  }, [applyTick, applyProductTick, applyAlert, setConnected, setCards, setProducts, setAlerts]);
}
