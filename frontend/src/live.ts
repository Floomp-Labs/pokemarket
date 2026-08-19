import { useEffect } from "react";
import { useStore } from "./store";

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
      const proto = location.protocol === "https:" ? "wss" : "ws";
      ws = new WebSocket(`${proto}://${location.host}/ws`);
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
