export interface CardSummary {
  id: string;
  name: string;
  set_id: string;
  set_name: string;
  number: string;
  rarity: string | null;
  image_small: string | null;
  price_type: string;
  latest_market: number | null;
  latest_ts: string | null;
  change_24h: number | null;
  change_7d: number | null;
  sparkline: number[];
  active_alert: boolean;
}

export interface VariantBlock {
  low?: number | null;
  mid?: number | null;
  high?: number | null;
  market?: number | null;
  directLow?: number | null;
}

export interface HistoryPoint {
  ts: string;
  low: number | null;
  mid: number | null;
  high: number | null;
  market: number | null;
  direct_low: number | null;
  estimated: boolean;
  cm_avg1: number | null;
  cm_avg7: number | null;
  cm_avg30: number | null;
  cm_trend: number | null;
  cm_avg_sell: number | null;
  cm_low: number | null;
  variants: Record<string, VariantBlock> | null;
}

export interface CardHistoryCard extends CardSummary {
  image_large: string | null;
}

export interface PsaGuide {
  ts: string;
  url: string | null;
  prices: Record<string, number>; // "ungraded" | "1".."9" | "9.5" | "10"
}

export interface SourcePrice {
  market?: number | null;
  low?: number | null;
  mid?: number | null;
  high?: number | null;
  direct_low?: number | null;
}

export interface CardHistory {
  card: CardHistoryCard;
  points: HistoryPoint[];
  alerts: AlertItem[];
  psa: PsaGuide | null;
  sources: Record<string, SourcePrice> | null;
}

export interface ProductSummary {
  id: string;
  name: string;
  set_name: string | null;
  url: string;
  image_small: string | null;
  price_kind: string;
  latest_price: number | null;
  latest_ts: string | null;
  change_24h: number | null;
  change_prev: number | null; // month-over-month (PriceCharting history is monthly)
  sparkline: number[];
  active_alert: boolean;
}

export interface ProductHistoryPoint {
  ts: string;
  price: number;
  estimated: boolean;
}

export interface ProductHistory {
  product: ProductSummary;
  points: ProductHistoryPoint[];
  alerts: AlertItem[];
  sources: Record<string, SourcePrice> | null;
}

export interface AlertItem {
  id: number;
  subject_id: string;
  subject_type: "card" | "product";
  name: string;
  image_small: string | null;
  ts: string;
  kind: string;
  severity: string;
  pct_change: number;
  z_score: number | null;
  message: string;
  acknowledged: boolean;
}

export interface SearchResult {
  id: string;
  name: string;
  set_id: string;
  set_name: string;
  number: string;
  rarity: string | null;
  image_small: string | null;
  price_type: string | null;
  market: number | null;
}

export interface ProductSearchResult {
  id: string;
  name: string;
  set_name: string | null;
  url: string;
  image_small: string | null;
  used: number | null;
  cib: number | null;
  new: number | null;
  price_kind: string | null;
  price: number | null;
}

export interface PriceTick {
  type: "price_tick";
  card_id: string;
  ts: string;
  market: number | null;
  low: number | null;
  mid: number | null;
  high: number | null;
  price_type: string;
}

export interface ProductTick {
  type: "product_tick";
  product_id: string;
  ts: string;
  price: number;
  price_kind: string;
}
