export interface PortfolioSummary {
  lifetime_pnl: number;
  lifetime_realized_pnl: number;
  lifetime_unrealized_pnl: number;
  lifetime_pnl_pct: number;
  lifetime_realized_pnl_pct: number;
  lifetime_unrealized_pnl_pct: number;
  ytd_pnl: number;
  ytd_realized_pnl: number;
  ytd_unrealized_pnl: number;
  ytd_pnl_pct: number;
  ytd_realized_pnl_pct: number;
  ytd_unrealized_pnl_pct: number;
  active_position_count: number;
  total_trade_count: number;
  first_trade_date: string | null;
  last_trade_date: string | null;
}

export interface OpenPosition {
  portfolio: string;
  side: string;
  shares: number;
  avg_cost: number;
  current_price: number;
  market_value: number;
  cost_basis: number;
  unrealized_pnl: number;
  unrealized_pnl_pct: number;
  realized_pnl: number;
  portfolio_pct: number;
  first_trade_date: string;
  last_trade_date: string;
}

export interface ClosedPositionSummary {
  portfolio: string;
  side: string;
  total_shares_traded: number;
  realized_pnl: number;
  first_trade_date: string;
  last_trade_date: string;
}

export interface TradeRecord {
  date: string;
  action: string;
  shares: number;
  price: number;
  portfolio: string;
  side: string;
  notional: number;
}

export interface PnlDataPoint {
  date: string;
  cumulative_pnl: number;
  realized_pnl: number;
  unrealized_pnl: number;
  cumulative_pnl_pct: number;
  realized_pnl_pct: number;
  unrealized_pnl_pct: number;
}

export interface PriceWeightDataPoint {
  date: string;
  stock_price: number | null;
  portfolio_pct: number;
}

export interface TickerPortfolioData {
  ticker: string;
  current_price: number;
  portfolios: string[];
  summary: PortfolioSummary;
  open_positions: OpenPosition[];
  closed_positions: ClosedPositionSummary[];
  trades: TradeRecord[];
  pnl_series: PnlDataPoint[];
  price_weight_series: PriceWeightDataPoint[];
}
