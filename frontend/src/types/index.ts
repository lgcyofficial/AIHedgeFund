export interface Trade {
  id: string;
  time: string;
  tick: number;
  agent: string;
  asset: string;
  action: 'BUY' | 'SELL' | 'HOLD';
  amount: number;
  quantity: number;
  price: number;
  confidence: number;
  reasoning: string;
  pnl: number;
  committee_approved: boolean;
  thesis: string;
  catalyst: string;
  expected_move: string;
  risk_flag?: string | null;
}

export interface PortfolioPosition {
  asset: string;
  quantity: number;
  average_cost: number;
  current_price: number;
  market_value: number;
  unrealized_pnl: number;
  weight: number;
  themes: Record<string, number>;
}

export interface ThemeExposure {
  theme: string;
  value: number;
  weight: number;
  assets: Record<string, number>;
}

export interface FactorExposure {
  factor: string;
  value: number;
  weight: number;
  assets: Record<string, number>;
}

export interface ConstructionAction {
  type: string;
  message: string;
  theme?: string | null;
  asset?: string | null;
  amount: number;
}

export interface PortfolioConstructionState {
  status: string;
  dominant_theme: string | null;
  cash_buffer_weight: number;
  concentration_score: number;
  actions: ConstructionAction[];
  notes: string[];
}

export interface PortfolioState {
  capital: number;
  cash: number;
  initial_capital: number;
  total_value: number;
  realized_pnl: number;
  unrealized_pnl: number;
  total_return_pct: number;
  positions: PortfolioPosition[];
  allocations: Record<string, number>;
  theme_exposures: ThemeExposure[];
  factor_exposures: FactorExposure[];
  construction: PortfolioConstructionState;
}

export interface AgentReasoning {
  agent: string;
  reasoning: string;
  decision: {
    asset: string;
    action: 'BUY' | 'SELL' | 'HOLD';
    amount: number;
    confidence: number;
    thesis?: string;
    catalyst?: string;
    expected_move?: string;
  };
}

export interface MarketState {
  prices: Record<string, number>;
  changes: Record<string, number>;
}

export interface NewsItem {
  title: string;
  time: string;
}

export interface BenchmarkState {
  values: Record<string, number>;
  returns: Record<string, number>;
}

export interface AgentLeaderboardEntry {
  agent: string;
  balance: number;
  deployed: number;
  realized_pnl: number;
  unrealized_pnl: number;
  trades_count: number;
  win_rate: number;
  last_decision: string;
  paused: boolean;
}

export interface CommitteeVoteRecord {
  agent: string;
  vote: 'YES' | 'NO';
  reasoning: string;
}

export interface CommitteeVoteEvent {
  proposal_agent: string;
  proposal: AgentReasoning['decision'];
  votes: CommitteeVoteRecord[];
  consensus: number;
  approved: boolean;
}

export interface RiskEvent {
  time: string;
  severity: 'medium' | 'high';
  message: string;
}

export interface ScenarioDefinition {
  id: string;
  title: string;
  description: string;
  shocks: Record<string, number>;
  headlines: string[];
}

export interface ControlState {
  session_active: boolean;
  risk: string;
  override_active: boolean;
  paused_agents: string[];
  active_scenario: string | null;
}

export interface SessionSummary {
  total_value: number;
  realized_pnl: number;
  unrealized_pnl: number;
  total_return_pct: number;
  trade_count: number;
  top_agent: string | null;
  benchmark_returns: Record<string, number>;
  headline: string;
}

export interface ResearchBrief {
  regime: string;
  summary: string;
  primary_risk: string;
  opportunities: string[];
  warnings: string[];
  watchlist: string[];
}

export interface BacktestRun {
  scenario_id: string;
  scenario_title: string;
  risk: string;
  return_pct: number;
  benchmark_return_pct: number;
  alpha_pct: number;
  max_drawdown_pct: number;
  trade_count: number;
  top_agent: string | null;
  verdict: string;
}

export interface BacktestLab {
  summary: string;
  best_run: BacktestRun | null;
  average_alpha_pct: number;
  beat_rate: number;
  runs: BacktestRun[];
}

export interface WebSocketMessageMap {
  portfolio_update: PortfolioState;
  trade_execution: Trade;
  agent_reasoning: AgentReasoning;
  agent_coordination: { message: string };
  market_update: MarketState;
  news_update: NewsItem[];
  treasury_update: { message: string; allocations: Record<string, number>; star: string; lagging: string };
  session_end: SessionSummary;
  committee_vote: CommitteeVoteEvent;
  benchmark_update: BenchmarkState;
  leaderboard_update: AgentLeaderboardEntry[];
  risk_event: RiskEvent;
  scenario_update: { active_scenario: string | null };
  control_state: ControlState;
  session_summary: SessionSummary;
  portfolio_construction: PortfolioConstructionState;
  research_update: ResearchBrief;
}

export type WebSocketMessage = {
  [K in keyof WebSocketMessageMap]: { type: K; data: WebSocketMessageMap[K] }
}[keyof WebSocketMessageMap];
