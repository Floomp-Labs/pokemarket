import { useEffect } from "react";
import { useStore } from "./store";

// Dev: same-origin /ws (Vite proxies to the backend). Production: derive
// from VITE_API_URL (https://api.example.com -> wss://api.example.com/ws).
const API_BASE = (import.meta.env.VITE_API_URL ?? "").replace(/\/$/, "");
const WS_URL = API_BASE
  ? `${API_BASE.replace(/^http/, "ws")}/ws`
  : `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`;

export function useLiveSocket() {
  const applyTick = useStore((s) => s.applyTick);
  const applyProductTick = useStore((s) => s.applyProductTick);
  const applyAlert = useStore((s) => s.applyAlert);
  const setConnected = useStore((s) => s.setConnected);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let closed = false;
    let retries = 0;
    let timer: number | undefined;

    const connect = () => {
      ws = new WebSocket(WS_URL);
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
        if (!closed) {
          const delay = Math.min(10_000, 500 * 2 ** retries++);
          timer = window.setTimeout(connect, delay);
        }
      };
    };
    connect();

    return () => {
      closed = true;
      window.clearTimeout(timer);
      ws?.close();
    };
  }, [applyTick, applyProductTick, applyAlert, setConnected]);
}
