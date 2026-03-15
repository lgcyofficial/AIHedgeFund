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
  category: string;
  sentiment: 'positive' | 'negative' | 'neutral';
  impact_score: number;
  assets: string[];
  source: string;
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

export interface AgentAllocation {
  agent: string;
  capital: number;
  cash: number;
  deployed: number;
  realized_pnl: number;
  unrealized_pnl: number;
  share_pct: number;
  last_decision: string;
  status: 'ACTIVE' | 'PAUSED' | 'COOLDOWN';
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

export interface ProjectionPoint {
  tick: number;
  time: string;
  total_value: number;
  actual_pnl: number;
  projected_pnl: number;
  projected_total_value: number;
  total_return_pct: number;
  projected_return_pct: number;
}

export interface ActivityEvent {
  id: string;
  time: string;
  kind: string;
  headline: string;
  message: string;
  tone: 'positive' | 'negative' | 'neutral';
  agent?: string | null;
  target_agent?: string | null;
  asset?: string | null;
  amount?: number | null;
  confidence?: number | null;
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
  allocation_update: AgentAllocation[];
  projection_update: ProjectionPoint;
  activity_event: ActivityEvent;
  risk_event: RiskEvent;
  scenario_update: { active_scenario: string | null };
  control_state: ControlState;
  session_summary: SessionSummary;
}

export type WebSocketMessage = {
  [K in keyof WebSocketMessageMap]: { type: K; data: WebSocketMessageMap[K] }
}[keyof WebSocketMessageMap];
