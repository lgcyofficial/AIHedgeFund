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


class AgentAllocation(BaseModel):
    agent: str
    capital: float
    cash: float
    deployed: float
    realized_pnl: float
    unrealized_pnl: float
    share_pct: float
    last_decision: str
    status: str


class ProjectionPoint(BaseModel):
    tick: int
    time: str
    total_value: float
    actual_pnl: float
    projected_pnl: float
    projected_total_value: float
    total_return_pct: float
    projected_return_pct: float


class NewsItem(BaseModel):
    title: str
    time: str
    category: str = "market"
    sentiment: str = "neutral"
    impact_score: float = 0.0
    assets: List[str] = []
    source: str = "Simulated Tape"


class ActivityEvent(BaseModel):
    id: str
    time: str
    kind: str
    headline: str
    message: str
    tone: str = "neutral"
    agent: Optional[str] = None
    target_agent: Optional[str] = None
    asset: Optional[str] = None
    amount: Optional[float] = None
    confidence: Optional[float] = None


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
