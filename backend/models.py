from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class Trade(BaseModel):
    id: str
    time: str
    tick: int
    agent: str
    asset: str
    action: str
    amount: float
    quantity: float
    price: float
    confidence: float
    reasoning: str
    pnl: float = 0.0
    committee_approved: bool = True
    thesis: str = ""
    catalyst: str = ""
    expected_move: str = ""
    risk_flag: Optional[str] = None


class PortfolioItem(BaseModel):
    asset: str
    quantity: float
    average_cost: float
    current_price: float
    market_value: float
    unrealized_pnl: float
    weight: float
    themes: Dict[str, float] = {}


class ThemeExposure(BaseModel):
    theme: str
    value: float
    weight: float
    assets: Dict[str, float]


class FactorExposure(BaseModel):
    factor: str
    value: float
    weight: float
    assets: Dict[str, float]


class ConstructionAction(BaseModel):
    type: str
    message: str
    theme: Optional[str] = None
    asset: Optional[str] = None
    amount: float = 0.0


class PortfolioConstructionState(BaseModel):
    status: str
    dominant_theme: Optional[str]
    cash_buffer_weight: float
    concentration_score: float
    actions: List[ConstructionAction]
    notes: List[str]


class Portfolio(BaseModel):
    capital: float
    cash: float
    initial_capital: float
    total_value: float
    realized_pnl: float
    unrealized_pnl: float
    total_return_pct: float
    positions: List[PortfolioItem]
    allocations: Dict[str, float]
    theme_exposures: List[ThemeExposure]
    factor_exposures: List[FactorExposure]
    construction: PortfolioConstructionState


class StartRequest(BaseModel):
    capital: float = 10000.0
    risk: str = "medium"
    duration: int = 60
    scenario: Optional[str] = None


class ScenarioRequest(BaseModel):
    scenario: str


class OverrideRequest(BaseModel):
    enabled: bool = False


class AgentControlRequest(BaseModel):
    agent: str
    paused: bool = False


class ScenarioDefinition(BaseModel):
    id: str
    title: str
    description: str
    shocks: Dict[str, float]
    headlines: List[str]


class VoteRecord(BaseModel):
    agent: str
    vote: str
    reasoning: str


class SessionSummary(BaseModel):
    total_value: float
    realized_pnl: float
    unrealized_pnl: float
    total_return_pct: float
    trade_count: int
    top_agent: Optional[str]
    benchmark_returns: Dict[str, float]
    headline: str


class ResearchBrief(BaseModel):
    regime: str
    summary: str
    primary_risk: str
    opportunities: List[str]
    warnings: List[str]
    watchlist: List[str]


class BacktestRun(BaseModel):
    scenario_id: str
    scenario_title: str
    risk: str
    return_pct: float
    benchmark_return_pct: float
    alpha_pct: float
    max_drawdown_pct: float
    trade_count: int
    top_agent: Optional[str]
    verdict: str


class BacktestLab(BaseModel):
    summary: str
    best_run: Optional[BacktestRun]
    average_alpha_pct: float
    beat_rate: float
    runs: List[BacktestRun]


class AgentSnapshot(BaseModel):
    agent: str
    balance: float
    deployed: float
    realized_pnl: float
    unrealized_pnl: float
    trades_count: int
    win_rate: float
    last_decision: str
    paused: bool = False
