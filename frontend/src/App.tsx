import { useEffect } from "react";
import { NavLink, Route, Routes } from "react-router-dom";
import { api } from "./api";
import { useLiveSocket } from "./live";
import { useStore } from "./store";
import Pokeball from "./components/Pokeball";
import Dashboard from "./pages/Dashboard";
import CardDetail from "./pages/CardDetail";
import ProductDetail from "./pages/ProductDetail";

export default function App() {
  const setCards = useStore((s) => s.setCards);
  const setProducts = useStore((s) => s.setProducts);
  const setAlerts = useStore((s) => s.setAlerts);
  const connected = useStore((s) => s.connected);
  const cardCount = useStore((s) => s.cards.length);
  const productCount = useStore((s) => s.products.length);
  useLiveSocket();

  useEffect(() => {
    const load = () => {
      api.listCards().then(setCards).catch(console.error);
      api.listProducts().then(setProducts).catch(console.error);
      api.alerts().then(setAlerts).catch(console.error);
    };
    load();
    const t = setInterval(load, 60_000);
    return () => clearInterval(t);
  }, [setCards, setProducts, setAlerts]);

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand-wrap">
          <NavLink to="/" className="brand-home">
            <Pokeball size={24} className="brand-ball" />
            <span className="brand">PokeMarket Agent</span>
          </NavLink>
          <span className="brand-tag">// TCG market intelligence</span>
        </div>
        <div className="topbar-right">
          <span className="topbar-meta">
            {cardCount} cards · {productCount} sealed tracked
          </span>
          <div className={`conn ${connected ? "on" : "off"}`}>
            <span className="dot" />
            {connected ? "live" : "reconnecting"}
          </div>
        </div>
      </header>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/card/:id" element={<CardDetail />} />
        <Route path="/product/:id" element={<ProductDetail />} />
      </Routes>
      <div className="bg-ball" aria-hidden="true">
        <Pokeball size={520} />
      </div>
    </div>
  );
}
