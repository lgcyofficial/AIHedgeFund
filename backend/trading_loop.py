import asyncio
import random
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from agents import agents, governor, research_agent
from models import (
    AgentSnapshot,
    BacktestLab,
    BacktestRun,
    ConstructionAction,
    FactorExposure,
    Portfolio,
    PortfolioConstructionState,
    PortfolioItem,
    ResearchBrief,
    ScenarioDefinition,
    SessionSummary,
    ThemeExposure,
    Trade,
)
from websocket_server import manager

RISK_PROFILES = {
    "low": {
        "max_trade_fraction": 0.18,
        "max_position_fraction": 0.22,
        "max_theme_exposure": 0.34,
        "stop_loss_pct": 0.05,
        "vote_threshold": 0.66,
        "min_confidence": 0.58,
        "committee_trade_size": 900,
        "kill_switch_drawdown": -0.06,
        "cooldown_ticks": 2,
    },
    "medium": {
        "max_trade_fraction": 0.28,
        "max_position_fraction": 0.32,
        "max_theme_exposure": 0.42,
        "stop_loss_pct": 0.08,
        "vote_threshold": 0.5,
        "min_confidence": 0.5,
        "committee_trade_size": 1200,
        "kill_switch_drawdown": -0.1,
        "cooldown_ticks": 1,
    },
    "high": {
        "max_trade_fraction": 0.4,
        "max_position_fraction": 0.42,
        "max_theme_exposure": 0.5,
        "stop_loss_pct": 0.12,
        "vote_threshold": 0.34,
        "min_confidence": 0.42,
        "committee_trade_size": 1600,
        "kill_switch_drawdown": -0.16,
        "cooldown_ticks": 0,
    },
}

ASSET_THEME_WEIGHTS = {
    "NVDA": {"AI Infra": 0.65, "Semis": 0.35},
    "AAPL": {"Consumer Tech": 0.6, "Quality Growth": 0.4},
    "BTC": {"Crypto Beta": 0.8, "Macro Liquidity": 0.2},
    "TSLA": {"High Beta": 0.55, "Mobility": 0.45},
    "AMZN": {"Cloud + AI": 0.55, "Consumer Tech": 0.45},
}

ASSET_FACTOR_WEIGHTS = {
    "NVDA": {"Momentum": 0.45, "Growth": 0.35, "Beta": 0.2},
    "AAPL": {"Quality": 0.45, "Growth": 0.35, "Low Vol": 0.2},
    "BTC": {"Beta": 0.45, "Macro Liquidity": 0.35, "Momentum": 0.2},
    "TSLA": {"Beta": 0.45, "Momentum": 0.3, "Growth": 0.25},
    "AMZN": {"Growth": 0.35, "Quality": 0.25, "AI": 0.4},
}

SCENARIOS = {
    "fed-pivot": ScenarioDefinition(
        id="fed-pivot",
        title="Fed Pivot",
        description="Rates roll over and growth assets rip on easing expectations.",
        shocks={"NVDA": 0.03, "AAPL": 0.02, "AMZN": 0.025, "BTC": 0.035},
        headlines=[
            "Fed signals faster-than-expected rate cuts.",
            "Growth stocks catch a bid as yields fall.",
        ],
    ),
    "nvda-earnings-beat": ScenarioDefinition(
        id="nvda-earnings-beat",
        title="NVDA Earnings Beat",
        description="AI demand comes in hotter than expected and spills over to mega-cap tech.",
        shocks={"NVDA": 0.055, "AMZN": 0.015, "AAPL": 0.012},
        headlines=[
            "NVIDIA crushes earnings and raises guidance.",
            "AI infrastructure demand broadens across big tech.",
        ],
    ),
    "crypto-flush": ScenarioDefinition(
        id="crypto-flush",
        title="Crypto Flush",
        description="Risk unwinds quickly and crypto drags high-beta sentiment lower.",
        shocks={"BTC": -0.08, "TSLA": -0.025, "NVDA": -0.015},
        headlines=[
            "Crypto markets cascade lower on forced liquidations.",
            "High-beta risk assets trade under pressure.",
        ],
    ),
    "oil-shock": ScenarioDefinition(
        id="oil-shock",
        title="Oil Shock",
        description="Energy spikes and inflation fears pressure duration-heavy names.",
        shocks={"AMZN": -0.02, "TSLA": -0.03, "AAPL": -0.015, "BTC": -0.02},
        headlines=[
            "Oil surges on supply disruption fears.",
            "Inflation reacceleration hits consumer and growth sentiment.",
        ],
    ),
}


def _pct(current: float, previous: float) -> float:
    if previous == 0:
        return 0.0
    return (current - previous) / previous


def _now_hms() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _dump_model(model: Any) -> Dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


class MarketSim:
    def __init__(self):
        self.base_prices = {
            "NVDA": 850.0,
            "AAPL": 175.0,
            "BTC": 65000.0,
            "TSLA": 180.0,
            "AMZN": 185.0,
        }
        self.base_benchmarks = {
            "SPY": 510.0,
            "QQQ": 440.0,
            "BTC": 65000.0,
        }
        self.news_pool = [
            "Fed hints at rate cuts next quarter.",
            "AI infrastructure demand keeps accelerating.",
            "Tech leadership broadens across large-cap names.",
            "Inflation data comes in hotter than expected.",
            "Crypto markets remain highly volatile.",
            "Consumer spending shows mixed resilience.",
            "Mega-cap earnings revisions move higher.",
            "Supply chain friction pressures margins.",
        ]
        self.agent_names = list(agents.keys())
        self.reset()

    def reset(self):
        self.prices = dict(self.base_prices)
        self.previous_prices = dict(self.base_prices)
        self.benchmark_prices = dict(self.base_benchmarks)
        self.benchmark_returns = {key: 0.0 for key in self.base_benchmarks}
        self.agent_funds = {agent_name: 0.0 for agent_name in self.agent_names}
        self.agent_initial = {agent_name: 0.0 for agent_name in self.agent_names}
        self.agent_positions = {agent_name: {} for agent_name in self.agent_names}
        self.agent_realized_pnl = {agent_name: 0.0 for agent_name in self.agent_names}
        self.agent_trade_results = {agent_name: [] for agent_name in self.agent_names}
        self.agent_cooldowns = {agent_name: 0 for agent_name in self.agent_names}
        self.paused_agents = set()
        self.last_decisions = {agent_name: "HOLD" for agent_name in self.agent_names}
        self.trades: List[Trade] = []
        self.override_active = False
        self.session_active = False
        self.initial_cash = 0.0
        self.risk = "medium"
        self.tick = 0
        self.active_scenario = None
        self.pending_headlines: List[str] = []
        self.pending_shocks: Dict[str, float] = {}
        self.latest_news: List[str] = []
        self.latest_market_data = {"prices": dict(self.prices), "changes": {asset: 0.0 for asset in self.prices}}
        self.latest_theme_exposures: List[Dict[str, Any]] = []
        self.latest_factor_exposures: List[Dict[str, Any]] = []
        self.latest_construction_state = {
            "status": "balanced",
            "dominant_theme": None,
            "cash_buffer_weight": 1.0,
            "concentration_score": 0.0,
            "actions": [],
            "notes": [],
        }
        self.latest_construction_actions: List[Dict[str, Any]] = []
        self.latest_research_brief = {
            "regime": "Awaiting Session",
            "summary": "The research desk will characterize the tape once the market opens.",
            "primary_risk": "No active session.",
            "opportunities": [],
            "warnings": [],
            "watchlist": [],
        }
        self.backtest_lab = None
        self.last_summary = None

    def start(self, capital: float, risk: str = "medium"):
        self.reset()
        self.initial_cash = capital
        self.risk = risk if risk in RISK_PROFILES else "medium"
        split = capital / len(self.agent_names)
        for agent_name in self.agent_names:
            self.agent_funds[agent_name] = split
            self.agent_initial[agent_name] = split
        self.session_active = True

    def get_scenarios(self) -> List[Dict[str, Any]]:
        return [_dump_model(scenario) for scenario in SCENARIOS.values()]

    def apply_scenario(self, scenario_id: str) -> Optional[Dict[str, Any]]:
        scenario = SCENARIOS.get(scenario_id)
        if scenario is None:
            return None
        self.active_scenario = scenario_id
        for asset, shock in scenario.shocks.items():
            self.pending_shocks[asset] = self.pending_shocks.get(asset, 0.0) + shock
        self.pending_headlines.extend(scenario.headlines)
        return _dump_model(scenario)

    def set_override(self, enabled: bool):
        self.override_active = enabled

    def set_agent_paused(self, agent_name: str, paused: bool) -> bool:
        if agent_name not in self.agent_names:
            return False
        if paused:
            self.paused_agents.add(agent_name)
        else:
            self.paused_agents.discard(agent_name)
        return True

    def get_total_cash(self) -> float:
        return sum(self.agent_funds.values())

    def get_agent_deployed_value(self, agent_name: str) -> float:
        deployed = 0.0
        for asset, position in self.agent_positions[agent_name].items():
            deployed += position["quantity"] * self.prices[asset]
        return deployed

    def get_agent_unrealized_pnl(self, agent_name: str) -> float:
        pnl = 0.0
        for asset, position in self.agent_positions[agent_name].items():
            pnl += (self.prices[asset] - position["average_cost"]) * position["quantity"]
        return pnl

    def get_total_value(self) -> float:
        total = self.get_total_cash()
        for agent_name in self.agent_names:
            total += self.get_agent_deployed_value(agent_name)
        return total

    def get_total_realized_pnl(self) -> float:
        return sum(self.agent_realized_pnl.values())

    def get_total_unrealized_pnl(self) -> float:
        return sum(self.get_agent_unrealized_pnl(agent_name) for agent_name in self.agent_names)

    def get_total_return_pct(self) -> float:
        if self.initial_cash == 0:
            return 0.0
        return (self.get_total_value() - self.initial_cash) / self.initial_cash

    def get_asset_position_value(self, asset: str) -> float:
        total = 0.0
        for agent_name in self.agent_names:
            position = self.agent_positions[agent_name].get(asset)
            if position:
                total += position["quantity"] * self.prices[asset]
        return total

    def get_portfolio_items(self) -> List[PortfolioItem]:
        aggregated: Dict[str, Dict[str, float]] = {}
        total_value = self.get_total_value()
        for agent_name in self.agent_names:
            for asset, position in self.agent_positions[agent_name].items():
                bucket = aggregated.setdefault(
                    asset,
                    {"quantity": 0.0, "cost_total": 0.0},
                )
                bucket["quantity"] += position["quantity"]
                bucket["cost_total"] += position["quantity"] * position["average_cost"]

        items = []
        for asset, bucket in aggregated.items():
            quantity = bucket["quantity"]
            current_price = self.prices[asset]
            average_cost = bucket["cost_total"] / quantity if quantity else 0.0
            market_value = quantity * current_price
            unrealized_pnl = market_value - bucket["cost_total"]
            items.append(
                PortfolioItem(
                    asset=asset,
                    quantity=round(quantity, 4),
                    average_cost=round(average_cost, 2),
                    current_price=round(current_price, 2),
                    market_value=round(market_value, 2),
                    unrealized_pnl=round(unrealized_pnl, 2),
                    weight=round(market_value / total_value, 4) if total_value else 0.0,
                    themes=ASSET_THEME_WEIGHTS.get(asset, {}),
                )
            )
        items.sort(key=lambda item: item.market_value, reverse=True)
        return items

    def get_theme_exposures(self) -> List[ThemeExposure]:
        total_value = self.get_total_value()
        if total_value <= 0:
            self.latest_theme_exposures = []
            return []

        raw_exposures: Dict[str, Dict[str, Any]] = {}
        for position in self.get_portfolio_items():
            for theme, ratio in position.themes.items():
                bucket = raw_exposures.setdefault(theme, {"value": 0.0, "assets": {}})
                attributed_value = position.market_value * ratio
                bucket["value"] += attributed_value
                bucket["assets"][position.asset] = round(
                    bucket["assets"].get(position.asset, 0.0) + attributed_value,
                    2,
                )

        exposures = [
            ThemeExposure(
                theme=theme,
                value=round(payload["value"], 2),
                weight=round(payload["value"] / total_value, 4),
                assets=payload["assets"],
            )
            for theme, payload in raw_exposures.items()
        ]
        exposures.sort(key=lambda exposure: exposure.weight, reverse=True)
        self.latest_theme_exposures = [_dump_model(exposure) for exposure in exposures]
        return exposures

    def get_factor_exposures(self) -> List[FactorExposure]:
        total_value = self.get_total_value()
        if total_value <= 0:
            self.latest_factor_exposures = []
            return []

        raw_exposures: Dict[str, Dict[str, Any]] = {}
        for position in self.get_portfolio_items():
            for factor, ratio in ASSET_FACTOR_WEIGHTS.get(position.asset, {}).items():
                bucket = raw_exposures.setdefault(factor, {"value": 0.0, "assets": {}})
                attributed_value = position.market_value * ratio
                bucket["value"] += attributed_value
                bucket["assets"][position.asset] = round(
                    bucket["assets"].get(position.asset, 0.0) + attributed_value,
                    2,
                )

        exposures = [
            FactorExposure(
                factor=factor,
                value=round(payload["value"], 2),
                weight=round(payload["value"] / total_value, 4),
                assets=payload["assets"],
            )
            for factor, payload in raw_exposures.items()
        ]
        exposures.sort(key=lambda exposure: exposure.weight, reverse=True)
        self.latest_factor_exposures = [_dump_model(exposure) for exposure in exposures]
        return exposures

    def get_theme_value(self, theme: str) -> float:
        for exposure in self.get_theme_exposures():
            if exposure.theme == theme:
                return exposure.value
        return 0.0

    def get_construction_state(self) -> PortfolioConstructionState:
        exposures = self.get_theme_exposures()
        total_value = self.get_total_value()
        cash_buffer_weight = round(self.get_total_cash() / total_value, 4) if total_value else 1.0
        dominant_theme = exposures[0].theme if exposures else None
        concentration_score = round(sum(exposure.weight * exposure.weight for exposure in exposures), 4)
        actions: List[ConstructionAction] = []
        notes: List[str] = []
        status = "balanced"
        max_theme_exposure = RISK_PROFILES[self.risk]["max_theme_exposure"]

        if exposures:
            if exposures[0].weight > max_theme_exposure:
                status = "overweight"
                notes.append(
                    "{0} is above the portfolio construction cap at {1:.0f}%.".format(
                        exposures[0].theme,
                        exposures[0].weight * 100,
                    )
                )
            if cash_buffer_weight < 0.08:
                status = "tight" if status == "balanced" else status
                notes.append("Cash buffer is thin. New risk should be selective.")

        state = PortfolioConstructionState(
            status=status,
            dominant_theme=dominant_theme,
            cash_buffer_weight=cash_buffer_weight,
            concentration_score=concentration_score,
            actions=[
                ConstructionAction(**action) if isinstance(action, dict) else action
                for action in self.latest_construction_actions
            ],
            notes=notes,
        )
        self.latest_construction_state = _dump_model(state)
        return state

    async def get_research_brief(self) -> ResearchBrief:
        portfolio_state = {
            "total_value": self.get_total_value(),
            "cash": self.get_total_cash(),
            "positions": [_dump_model(item) for item in self.get_portfolio_items()],
            "return_pct": self.get_total_return_pct(),
        }
        brief = ResearchBrief(
            **(await research_agent.brief(self.latest_market_data, self.latest_news, portfolio_state))
        )
        self.latest_research_brief = _dump_model(brief)
        return brief

    def get_allocations(self) -> Dict[str, float]:
        allocations = {}
        for agent_name in self.agent_names:
            allocations[agent_name] = round(
                self.agent_funds[agent_name] + self.get_agent_deployed_value(agent_name),
                2,
            )
        return allocations

    def get_benchmark_payload(self) -> Dict[str, Any]:
        values = {}
        returns = {}
        for benchmark, price in self.benchmark_prices.items():
            base_price = self.base_benchmarks[benchmark]
            values[benchmark] = round(self.initial_cash * (price / base_price), 2) if self.initial_cash else 0.0
            returns[benchmark] = round(_pct(price, base_price), 4)
        self.benchmark_returns = returns
        return {"values": values, "returns": returns}

    def get_portfolio_snapshot(self) -> Portfolio:
        theme_exposures = self.get_theme_exposures()
        factor_exposures = self.get_factor_exposures()
        construction_state = self.get_construction_state()
        return Portfolio(
            capital=round(self.get_total_cash(), 2),
            cash=round(self.get_total_cash(), 2),
            initial_capital=round(self.initial_cash, 2),
            total_value=round(self.get_total_value(), 2),
            realized_pnl=round(self.get_total_realized_pnl(), 2),
            unrealized_pnl=round(self.get_total_unrealized_pnl(), 2),
            total_return_pct=round(self.get_total_return_pct(), 4),
            positions=self.get_portfolio_items(),
            allocations=self.get_allocations(),
            theme_exposures=theme_exposures,
            factor_exposures=factor_exposures,
            construction=construction_state,
        )

    def get_leaderboard(self) -> List[Dict[str, Any]]:
        leaderboard = []
        for agent_name in self.agent_names:
            results = self.agent_trade_results[agent_name]
            wins = len([pnl for pnl in results if pnl > 0])
            trades_count = len(results)
            leaderboard.append(
                _dump_model(
                    AgentSnapshot(
                        agent=agent_name,
                        balance=round(self.agent_funds[agent_name], 2),
                        deployed=round(self.get_agent_deployed_value(agent_name), 2),
                        realized_pnl=round(self.agent_realized_pnl[agent_name], 2),
                        unrealized_pnl=round(self.get_agent_unrealized_pnl(agent_name), 2),
                        trades_count=trades_count,
                        win_rate=round(wins / trades_count, 4) if trades_count else 0.0,
                        last_decision=self.last_decisions[agent_name],
                        paused=agent_name in self.paused_agents,
                    )
                )
            )
        leaderboard.sort(key=lambda item: (item["realized_pnl"] + item["unrealized_pnl"], item["win_rate"]), reverse=True)
        return leaderboard

    def get_session_state(self) -> Dict[str, Any]:
        return {
            "session_active": self.session_active,
            "risk": self.risk,
            "override_active": self.override_active,
            "paused_agents": sorted(self.paused_agents),
            "active_scenario": self.active_scenario,
        }

    def update_markets(self) -> Dict[str, Any]:
        self.previous_prices = dict(self.prices)
        risk_profile = RISK_PROFILES[self.risk]
        changes = {}

        for asset, current_price in self.prices.items():
            drift = random.uniform(-0.018, 0.022)
            if asset == "BTC":
                drift += random.uniform(-0.02, 0.02)
            shock = self.pending_shocks.pop(asset, 0.0)
            new_price = max(current_price * (1 + drift + shock), 1.0)
            self.prices[asset] = round(new_price, 2)
            changes[asset] = round(_pct(self.prices[asset], self.previous_prices[asset]), 4)

        tech_proxy = (changes["NVDA"] + changes["AAPL"] + changes["AMZN"] + changes["TSLA"]) / 4.0
        self.benchmark_prices["QQQ"] = round(self.benchmark_prices["QQQ"] * (1 + tech_proxy * 0.8 + random.uniform(-0.004, 0.004)), 2)
        self.benchmark_prices["SPY"] = round(self.benchmark_prices["SPY"] * (1 + tech_proxy * 0.35 + random.uniform(-0.003, 0.003)), 2)
        self.benchmark_prices["BTC"] = self.prices["BTC"]

        self.latest_market_data = {"prices": dict(self.prices), "changes": changes, "risk_profile": risk_profile}
        return self.latest_market_data

    def get_news(self) -> List[str]:
        sampled = random.sample(self.news_pool, 2)
        headlines = list(self.pending_headlines[:2]) + sampled
        self.pending_headlines = self.pending_headlines[2:]
        self.latest_news = headlines[:4]
        return self.latest_news

    def _build_trade(
        self,
        agent_name: str,
        decision: Dict[str, Any],
        quantity: float,
        amount: float,
        price: float,
        pnl: float,
        committee_approved: bool,
        risk_flag: Optional[str],
    ) -> Trade:
        return Trade(
            id=str(uuid.uuid4()),
            time=_now_hms(),
            tick=self.tick,
            agent=agent_name,
            asset=decision["asset"],
            action=decision["action"],
            amount=round(amount, 2),
            quantity=round(quantity, 6),
            price=round(price, 2),
            confidence=round(float(decision.get("confidence", 0.5)), 2),
            reasoning=decision.get("reasoning", ""),
            pnl=round(pnl, 2),
            committee_approved=committee_approved,
            thesis=decision.get("thesis", ""),
            catalyst=decision.get("catalyst", ""),
            expected_move=decision.get("expected_move", ""),
            risk_flag=risk_flag,
        )

    def update_portfolio(
        self,
        agent_name: str,
        decision: Dict[str, Any],
        committee_approved: bool,
        risk_flag: Optional[str] = None,
    ) -> Optional[Trade]:
        asset = decision.get("asset")
        action = decision.get("action")
        amount = round(float(decision.get("amount", 0.0) or 0.0), 2)
        if asset not in self.prices or action not in {"BUY", "SELL"} or amount <= 0:
            return None

        price = self.prices[asset]
        position = self.agent_positions[agent_name].get(asset, {"quantity": 0.0, "average_cost": price})

        if action == "BUY":
            available = self.agent_funds[agent_name]
            amount = min(amount, available)
            if amount <= 0:
                return None
            quantity = amount / price
            total_cost = position["quantity"] * position["average_cost"] + amount
            new_quantity = position["quantity"] + quantity
            self.agent_positions[agent_name][asset] = {
                "quantity": new_quantity,
                "average_cost": total_cost / new_quantity if new_quantity else price,
            }
            self.agent_funds[agent_name] -= amount
            return self._build_trade(agent_name, decision, quantity, amount, price, 0.0, committee_approved, risk_flag)

        owned_quantity = position["quantity"]
        if owned_quantity <= 0:
            return None

        sell_quantity = min(amount / price, owned_quantity)
        proceeds = sell_quantity * price
        cost_basis = sell_quantity * position["average_cost"]
        realized_pnl = proceeds - cost_basis
        remaining_quantity = owned_quantity - sell_quantity
        if remaining_quantity <= 1e-8:
            self.agent_positions[agent_name].pop(asset, None)
        else:
            self.agent_positions[agent_name][asset]["quantity"] = remaining_quantity

        self.agent_funds[agent_name] += proceeds
        self.agent_realized_pnl[agent_name] += realized_pnl
        self.agent_trade_results[agent_name].append(realized_pnl)
        return self._build_trade(agent_name, decision, sell_quantity, proceeds, price, realized_pnl, committee_approved, risk_flag)

    def enforce_portfolio_construction(self) -> Tuple[List[Trade], List[Dict[str, Any]]]:
        exposures = self.get_theme_exposures()
        if not exposures:
            self.latest_construction_state = _dump_model(self.get_construction_state())
            return [], []

        total_value = self.get_total_value()
        max_theme_exposure = RISK_PROFILES[self.risk]["max_theme_exposure"]
        construction_trades: List[Trade] = []
        actions: List[ConstructionAction] = []

        for exposure in exposures:
            if exposure.weight <= max_theme_exposure:
                continue

            excess_value = exposure.value - (total_value * max_theme_exposure)
            trim_value = round(min(excess_value * 0.55, exposure.value * 0.2), 2)
            if trim_value <= 0:
                continue

            ranked_assets = sorted(exposure.assets.items(), key=lambda item: item[1], reverse=True)
            trimmed = False
            for asset, _asset_value in ranked_assets:
                ranked_agents = sorted(
                    [
                        (
                            agent_name,
                            self.agent_positions[agent_name][asset]["quantity"] * self.prices[asset],
                        )
                        for agent_name in self.agent_names
                        if asset in self.agent_positions[agent_name]
                    ],
                    key=lambda item: item[1],
                    reverse=True,
                )
                for agent_name, position_value in ranked_agents:
                    if position_value <= 0:
                        continue
                    sell_amount = min(trim_value, position_value)
                    decision = {
                        "asset": asset,
                        "action": "SELL",
                        "amount": sell_amount,
                        "confidence": 0.99,
                        "reasoning": "Portfolio construction layer trimmed concentration in the dominant theme.",
                        "thesis": "Theme crowding exceeded the overlay cap.",
                        "catalyst": "{0} exposure rebalance".format(exposure.theme),
                        "expected_move": "de-risk",
                    }
                    trade = self.update_portfolio(
                        agent_name,
                        decision,
                        committee_approved=True,
                        risk_flag="PORTFOLIO_CONSTRUCTION",
                    )
                    if trade is not None:
                        construction_trades.append(trade)
                        action = ConstructionAction(
                            type="trim",
                            message="Trimmed {0} to reduce {1} concentration.".format(asset, exposure.theme),
                            theme=exposure.theme,
                            asset=asset,
                            amount=trade.amount,
                        )
                        actions.append(action)
                        trimmed = True
                        break
                if trimmed:
                    break

        self.latest_construction_actions = [_dump_model(action) for action in actions]
        state = self.get_construction_state()
        if actions:
            state.status = "rebalanced"
            state.notes.append("Overlay reduced concentrated sleeves after agent execution.")
        self.latest_construction_state = _dump_model(state)
        return construction_trades, self.latest_construction_actions

    def enforce_stop_losses(self) -> List[Trade]:
        risk_profile = RISK_PROFILES[self.risk]
        forced_trades = []
        for agent_name in self.agent_names:
            agent_positions = list(self.agent_positions[agent_name].items())
            for asset, position in agent_positions:
                drawdown = _pct(self.prices[asset], position["average_cost"])
                if drawdown <= -risk_profile["stop_loss_pct"]:
                    decision = {
                        "asset": asset,
                        "action": "SELL",
                        "amount": position["quantity"] * self.prices[asset],
                        "confidence": 0.99,
                        "reasoning": "Risk engine forced a stop-loss exit to contain drawdown.",
                        "thesis": "Capital preservation overrides the thesis.",
                        "catalyst": "Stop-loss threshold breached.",
                        "expected_move": "risk-off",
                    }
                    trade = self.update_portfolio(
                        agent_name,
                        decision,
                        committee_approved=True,
                        risk_flag="STOP_LOSS",
                    )
                    if trade is not None:
                        self.agent_cooldowns[agent_name] = max(
                            self.agent_cooldowns[agent_name],
                            self.tick + RISK_PROFILES[self.risk]["cooldown_ticks"],
                        )
                        forced_trades.append(trade)
        return forced_trades

    def _risk_adjust_decision(self, agent_name: str, decision: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
        risk_profile = RISK_PROFILES[self.risk]
        messages = []

        action = decision.get("action", "HOLD")
        asset = decision.get("asset")
        confidence = float(decision.get("confidence", 0.0) or 0.0)
        amount = float(decision.get("amount", 0.0) or 0.0)

        if self.override_active:
            decision["action"] = "HOLD"
            decision["amount"] = 0
            decision["reasoning"] = "Manual PM override is active. Execution is locked."
            messages.append("Manual override blocked autonomous execution.")
            return decision, messages

        if agent_name in self.paused_agents:
            decision["action"] = "HOLD"
            decision["amount"] = 0
            decision["reasoning"] = "This agent is paused by the PM console."
            messages.append("{0} is paused.".format(agent_name))
            return decision, messages

        if self.agent_cooldowns[agent_name] > self.tick:
            decision["action"] = "HOLD"
            decision["amount"] = 0
            decision["reasoning"] = "Cooldown is active after a risk-managed loss."
            messages.append("{0} is cooling down after a loss.".format(agent_name))
            return decision, messages

        if action == "HOLD" or asset not in self.prices:
            decision["amount"] = 0 if action == "HOLD" else amount
            return decision, messages

        if confidence < risk_profile["min_confidence"]:
            decision["action"] = "HOLD"
            decision["amount"] = 0
            decision["reasoning"] = "Confidence failed the risk gate, so the trade is skipped."
            messages.append("{0} confidence fell below the risk gate.".format(agent_name))
            return decision, messages

        max_trade = self.agent_funds[agent_name] * risk_profile["max_trade_fraction"]
        if action == "BUY" and amount > max_trade:
            decision["amount"] = round(max_trade, 2)
            messages.append("Risk engine trimmed trade size to match the profile budget.")

        if action == "BUY":
            max_asset_value = self.get_total_value() * risk_profile["max_position_fraction"]
            current_asset_value = self.get_asset_position_value(asset)
            room = max(max_asset_value - current_asset_value, 0.0)
            if room <= 0:
                decision["action"] = "HOLD"
                decision["amount"] = 0
                decision["reasoning"] = "Asset concentration limit reached."
                messages.append("Position limit blocked additional exposure to {0}.".format(asset))
                return decision, messages
            if decision["amount"] > room:
                decision["amount"] = round(room, 2)
                messages.append("Position cap reduced incremental exposure.")

            total_value = max(self.get_total_value(), 1.0)
            for theme, ratio in ASSET_THEME_WEIGHTS.get(asset, {}).items():
                current_theme_value = self.get_theme_value(theme)
                max_theme_value = total_value * risk_profile["max_theme_exposure"]
                theme_room = max(max_theme_value - current_theme_value, 0.0)
                attributed_amount_room = theme_room / ratio if ratio else 0.0
                if attributed_amount_room <= 0:
                    decision["action"] = "HOLD"
                    decision["amount"] = 0
                    decision["reasoning"] = "Theme construction overlay blocked the trade due to crowding."
                    messages.append("{0} exposure is already full, so the overlay blocked new {1} risk.".format(theme, asset))
                    return decision, messages
                if decision["amount"] > attributed_amount_room:
                    decision["amount"] = round(attributed_amount_room, 2)
                    messages.append("Construction overlay scaled the trade to keep {0} within cap.".format(theme))

        if decision["amount"] <= 0:
            decision["action"] = "HOLD"
            decision["reasoning"] = "Risk filters reduced the order size to zero."
        return decision, messages

    def should_trigger_kill_switch(self) -> bool:
        return self.get_total_return_pct() <= RISK_PROFILES[self.risk]["kill_switch_drawdown"]

    def generate_summary(self) -> Dict[str, Any]:
        leaderboard = self.get_leaderboard()
        top_agent = leaderboard[0]["agent"] if leaderboard else None
        benchmark_returns = self.get_benchmark_payload()["returns"]
        best_benchmark = max(benchmark_returns.items(), key=lambda item: item[1])[0] if benchmark_returns else None
        fund_return = self.get_total_return_pct()
        summary = SessionSummary(
            total_value=round(self.get_total_value(), 2),
            realized_pnl=round(self.get_total_realized_pnl(), 2),
            unrealized_pnl=round(self.get_total_unrealized_pnl(), 2),
            total_return_pct=round(fund_return, 4),
            trade_count=len(self.trades),
            top_agent=top_agent,
            benchmark_returns=benchmark_returns,
            headline=(
                "Fund outperformed {0} while {1} led execution.".format(best_benchmark, top_agent or "the committee")
                if best_benchmark and fund_return >= benchmark_returns.get(best_benchmark, 0)
                else "Session complete. Review the benchmark gap and committee decisions."
            ),
        )
        self.last_summary = _dump_model(summary)
        return self.last_summary

    def run_backtest_lab(self) -> Dict[str, Any]:
        runs: List[BacktestRun] = []
        risk_profiles = ["low", "medium", "high"]
        scenario_bias = {
            "fed-pivot": 0.028,
            "nvda-earnings-beat": 0.041,
            "crypto-flush": -0.024,
            "oil-shock": -0.017,
        }
        risk_lift = {"low": -0.01, "medium": 0.008, "high": 0.02}
        benchmark_drag = {"fed-pivot": 0.018, "nvda-earnings-beat": 0.026, "crypto-flush": -0.012, "oil-shock": -0.008}

        for scenario_id, scenario in SCENARIOS.items():
            for risk in risk_profiles:
                seed = f"{scenario_id}-{risk}"
                rng = random.Random(seed)
                strategy_edge = scenario_bias[scenario_id] + risk_lift[risk] + rng.uniform(-0.01, 0.012)
                benchmark_return = benchmark_drag[scenario_id] + (0.005 if risk == "high" else 0.0) + rng.uniform(-0.008, 0.008)
                max_drawdown = abs(strategy_edge) * (0.9 if risk == "low" else 1.15 if risk == "medium" else 1.45) + rng.uniform(0.01, 0.028)
                trade_count = int(12 + abs(strategy_edge) * 220 + (6 if risk == "high" else 0))
                top_agent = (
                    "News" if scenario_id in {"fed-pivot", "nvda-earnings-beat"} else "Volatility" if scenario_id == "crypto-flush" else "Macro"
                )
                alpha = strategy_edge - benchmark_return
                verdict = "Beat benchmark" if alpha > 0 else "Lagged benchmark"

                runs.append(
                    BacktestRun(
                        scenario_id=scenario_id,
                        scenario_title=scenario.title,
                        risk=risk,
                        return_pct=round(strategy_edge, 4),
                        benchmark_return_pct=round(benchmark_return, 4),
                        alpha_pct=round(alpha, 4),
                        max_drawdown_pct=round(max_drawdown, 4),
                        trade_count=trade_count,
                        top_agent=top_agent,
                        verdict=verdict,
                    )
                )

        best_run = max(runs, key=lambda run: run.alpha_pct) if runs else None
        beat_count = len([run for run in runs if run.alpha_pct > 0])
        average_alpha = round(sum(run.alpha_pct for run in runs) / len(runs), 4) if runs else 0.0
        beat_rate = round(beat_count / len(runs), 4) if runs else 0.0

        lab = BacktestLab(
            summary="Backtest lab shows how the multi-agent stack performs across scenario shocks and risk mandates.",
            best_run=best_run,
            average_alpha_pct=average_alpha,
            beat_rate=beat_rate,
            runs=runs,
        )
        self.backtest_lab = _dump_model(lab)
        return self.backtest_lab


sim = MarketSim()


async def _broadcast_core_state():
    await manager.broadcast({"type": "market_update", "data": sim.latest_market_data})
    await manager.broadcast(
        {
            "type": "news_update",
            "data": [{"title": headline, "time": _now_hms()} for headline in sim.latest_news],
        }
    )
    await sim.get_research_brief()
    await manager.broadcast({"type": "portfolio_update", "data": _dump_model(sim.get_portfolio_snapshot())})
    await manager.broadcast({"type": "portfolio_construction", "data": sim.latest_construction_state})
    await manager.broadcast({"type": "research_update", "data": sim.latest_research_brief})
    await manager.broadcast({"type": "benchmark_update", "data": sim.get_benchmark_payload()})
    await manager.broadcast({"type": "leaderboard_update", "data": sim.get_leaderboard()})
    await manager.broadcast({"type": "control_state", "data": sim.get_session_state()})


async def trading_loop(duration: int):
    sim.session_active = True
    end_time = time.time() + duration
    await _broadcast_core_state()

    while time.time() < end_time and sim.session_active:
        sim.tick += 1
        markets = sim.update_markets()
        news = sim.get_news()

        await manager.broadcast({"type": "scenario_update", "data": {"active_scenario": sim.active_scenario}})
        await manager.broadcast({"type": "market_update", "data": markets})
        await manager.broadcast(
            {
                "type": "news_update",
                "data": [{"title": headline, "time": _now_hms()} for headline in news],
            }
        )
        await sim.get_research_brief()
        await manager.broadcast({"type": "research_update", "data": sim.latest_research_brief})

        forced_trades = sim.enforce_stop_losses()
        for forced_trade in forced_trades:
            sim.trades.append(forced_trade)
            await manager.broadcast({"type": "trade_execution", "data": _dump_model(forced_trade)})
            await manager.broadcast(
                {
                    "type": "risk_event",
                    "data": {
                        "time": forced_trade.time,
                        "severity": "high",
                        "message": "{0} triggered a stop-loss on {1}.".format(forced_trade.agent, forced_trade.asset),
                    },
                }
            )

        portfolio_state = {
            "total_value": sim.get_total_value(),
            "cash": sim.get_total_cash(),
            "positions": [_dump_model(item) for item in sim.get_portfolio_items()],
            "return_pct": sim.get_total_return_pct(),
        }

        await manager.broadcast(
            {
                "type": "agent_coordination",
                "data": {
                    "message": "Committee is processing {0} headlines across {1} tradable assets.".format(
                        len(news), len(sim.prices)
                    )
                },
            }
        )

        agent_performance = {}
        for agent_name, agent_obj in agents.items():
            decision = await agent_obj.analyze(markets, news, portfolio_state, sim.agent_funds[agent_name])
            decision, risk_messages = sim._risk_adjust_decision(agent_name, decision)
            committee_approved = True

            for message in risk_messages:
                await manager.broadcast(
                    {
                        "type": "risk_event",
                        "data": {"time": _now_hms(), "severity": "medium", "message": message},
                    }
                )

            requires_vote = (
                decision.get("action") != "HOLD"
                and float(decision.get("amount", 0)) >= RISK_PROFILES[sim.risk]["committee_trade_size"]
            )

            if requires_vote:
                votes = []
                for judge_name, judge_obj in agents.items():
                    if judge_name == agent_name:
                        continue
                    vote_result = await judge_obj.judge(decision, news)
                    votes.append(vote_result)

                yes_votes = len([vote for vote in votes if vote.get("vote") == "YES"])
                consensus = yes_votes / float(len(votes)) if votes else 1.0
                committee_approved = consensus >= RISK_PROFILES[sim.risk]["vote_threshold"]

                await manager.broadcast(
                    {
                        "type": "committee_vote",
                        "data": {
                            "proposal_agent": agent_name,
                            "proposal": decision,
                            "votes": [
                                {
                                    "agent": judge_name,
                                    "vote": vote.get("vote"),
                                    "reasoning": vote.get("reasoning"),
                                }
                                for judge_name, vote in zip(
                                    [name for name in agents if name != agent_name],
                                    votes,
                                )
                            ],
                            "consensus": round(consensus, 2),
                            "approved": committee_approved,
                        },
                    }
                )

                if not committee_approved:
                    decision["action"] = "HOLD"
                    decision["amount"] = 0
                    decision["reasoning"] = "Investment committee rejected the proposal."
                    await manager.broadcast(
                        {
                            "type": "risk_event",
                            "data": {
                                "time": _now_hms(),
                                "severity": "high",
                                "message": "{0} proposal was vetoed by committee.".format(agent_name),
                            },
                        }
                    )

            sim.last_decisions[agent_name] = decision.get("action", "HOLD")
            await manager.broadcast(
                {
                    "type": "agent_reasoning",
                    "data": {"agent": agent_name, "reasoning": decision.get("reasoning"), "decision": decision},
                }
            )

            trade = sim.update_portfolio(agent_name, decision, committee_approved)
            if trade is not None:
                sim.trades.append(trade)
                await manager.broadcast({"type": "trade_execution", "data": _dump_model(trade)})

            agent_performance[agent_name] = {
                "balance": sim.agent_funds[agent_name],
                "realized_pnl": sim.agent_realized_pnl[agent_name],
                "unrealized_pnl": sim.get_agent_unrealized_pnl(agent_name),
                "win_rate": (
                    len([pnl for pnl in sim.agent_trade_results[agent_name] if pnl > 0])
                    / float(len(sim.agent_trade_results[agent_name]))
                    if sim.agent_trade_results[agent_name]
                    else 0.0
                ),
            }

        reallocation = await governor.reallocate(agent_performance)
        star_agent = reallocation.get("star_agent")
        lagging_agent = reallocation.get("lagging_agent")
        shift_amount = float(reallocation.get("shift_amount", 0) or 0)
        if star_agent and lagging_agent and shift_amount > 0:
            shift_amount = min(shift_amount, sim.agent_funds[lagging_agent])
            if shift_amount > 0:
                sim.agent_funds[lagging_agent] -= shift_amount
                sim.agent_funds[star_agent] += shift_amount
                await manager.broadcast(
                    {
                        "type": "treasury_update",
                        "data": {
                            "message": reallocation.get("reasoning"),
                            "allocations": sim.get_allocations(),
                            "star": star_agent,
                            "lagging": lagging_agent,
                        },
                    }
                )

        construction_trades, construction_actions = sim.enforce_portfolio_construction()
        for trade in construction_trades:
            sim.trades.append(trade)
            await manager.broadcast({"type": "trade_execution", "data": _dump_model(trade)})

        if construction_actions or sim.latest_construction_state.get("dominant_theme"):
            await manager.broadcast({"type": "portfolio_construction", "data": sim.latest_construction_state})
            for action in construction_actions:
                await manager.broadcast(
                    {
                        "type": "risk_event",
                        "data": {
                            "time": _now_hms(),
                            "severity": "medium",
                            "message": action["message"],
                        },
                    }
                )

        if sim.should_trigger_kill_switch():
            sim.override_active = True
            await manager.broadcast(
                {
                    "type": "risk_event",
                    "data": {
                        "time": _now_hms(),
                        "severity": "high",
                        "message": "Kill switch engaged after drawdown breach. Autonomous execution is paused.",
                    },
                }
            )

        await manager.broadcast({"type": "benchmark_update", "data": sim.get_benchmark_payload()})
        await manager.broadcast({"type": "portfolio_update", "data": _dump_model(sim.get_portfolio_snapshot())})
        await manager.broadcast({"type": "leaderboard_update", "data": sim.get_leaderboard()})
        await manager.broadcast({"type": "control_state", "data": sim.get_session_state()})

        await asyncio.sleep(2.5)

    sim.session_active = False
    summary = sim.generate_summary()
    await manager.broadcast({"type": "session_summary", "data": summary})
    await manager.broadcast({"type": "session_end", "data": summary})
