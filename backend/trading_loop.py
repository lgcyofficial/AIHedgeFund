import asyncio
import os
import random
import re
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from agents import agents, governor
from models import (
    ActivityEvent,
    AgentAllocation,
    AgentSnapshot,
    NewsItem,
    Portfolio,
    PortfolioItem,
    ProjectionPoint,
    ScenarioDefinition,
    SessionSummary,
    Trade,
)
from news_service import LiveNewsService
from websocket_server import manager

TICK_DELAY_SECONDS = float(os.getenv("TRADING_TICK_DELAY_SECONDS", "0.5"))
TRADE_IMPACT_MIN_PCT = float(os.getenv("TRADE_IMPACT_MIN_PCT", "0.0025"))
TRADE_IMPACT_MAX_PCT = float(os.getenv("TRADE_IMPACT_MAX_PCT", "0.012"))

RISK_PROFILES = {
    "low": {
        "max_trade_fraction": 0.18,
        "max_position_fraction": 0.22,
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
        "stop_loss_pct": 0.12,
        "vote_threshold": 0.34,
        "min_confidence": 0.42,
        "committee_trade_size": 1600,
        "kill_switch_drawdown": -0.16,
        "cooldown_ticks": 0,
    },
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


def _parse_expected_move(text: str) -> float:
    numbers = [float(value) for value in re.findall(r"\d+(?:\.\d+)?", text or "")]
    if not numbers:
        return 0.0
    midpoint = sum(numbers[:2]) / len(numbers[:2])
    return midpoint / 100.0


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


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
        self.latest_news_items: List[Dict[str, Any]] = []
        self.latest_market_data = {"prices": dict(self.prices), "changes": {asset: 0.0 for asset in self.prices}}
        self.latest_projection: Optional[Dict[str, Any]] = None
        self.projection_history: List[Dict[str, Any]] = []
        self.activity_log: List[Dict[str, Any]] = []
        self.latest_agent_signals: Dict[str, Dict[str, Any]] = {}
        self.last_summary = None

    def _get_initial_agent_weights(self, scenario_id: Optional[str] = None) -> Dict[str, float]:
        if self.risk == "low":
            weights = {"Momentum": 0.2, "News": 0.22, "Macro": 0.38, "Volatility": 0.2}
        elif self.risk == "high":
            weights = {"Momentum": 0.3, "News": 0.24, "Macro": 0.16, "Volatility": 0.3}
        else:
            weights = {"Momentum": 0.27, "News": 0.25, "Macro": 0.23, "Volatility": 0.25}

        scenario_biases = {
            "fed-pivot": {"Momentum": 0.03, "News": 0.02, "Macro": 0.01, "Volatility": -0.06},
            "nvda-earnings-beat": {"Momentum": 0.05, "News": 0.05, "Macro": -0.04, "Volatility": -0.06},
            "crypto-flush": {"Momentum": -0.05, "News": -0.02, "Macro": 0.02, "Volatility": 0.05},
            "oil-shock": {"Momentum": -0.04, "News": -0.01, "Macro": 0.03, "Volatility": 0.02},
        }
        if scenario_id in scenario_biases:
            for agent_name, bias in scenario_biases[scenario_id].items():
                weights[agent_name] = max(0.08, weights[agent_name] + bias)

        total = sum(weights.values()) or 1.0
        return {agent_name: weight / total for agent_name, weight in weights.items()}

    def start(self, capital: float, risk: str = "medium", scenario_id: Optional[str] = None):
        self.reset()
        self.initial_cash = capital
        self.risk = risk if risk in RISK_PROFILES else "medium"
        self.active_scenario = scenario_id if scenario_id in SCENARIOS else None
        weights = self._get_initial_agent_weights(self.active_scenario)
        allocated_total = 0.0
        for index, agent_name in enumerate(self.agent_names):
            if index == len(self.agent_names) - 1:
                amount = round(capital - allocated_total, 2)
            else:
                amount = round(capital * weights.get(agent_name, 0.0), 2)
                allocated_total += amount
            self.agent_funds[agent_name] = amount
            self.agent_initial[agent_name] = amount
        if self.active_scenario:
            self.apply_scenario(self.active_scenario)
        self.session_active = True
        self.capture_projection()

    def get_dynamic_allocation_shift(self, agent_stats: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        scores: Dict[str, float] = {}
        for agent_name in self.agent_names:
            stats = agent_stats.get(agent_name, {})
            signal = self.latest_agent_signals.get(agent_name, {})
            confidence = float(signal.get("confidence", 0.45) or 0.45)
            action = signal.get("action", "HOLD")
            signal_bonus = confidence if action != "HOLD" else confidence * 0.35
            pnl_score = max(-0.5, min((stats.get("realized_pnl", 0.0) + stats.get("unrealized_pnl", 0.0)) / max(self.initial_cash, 1.0) * 18, 1.5))
            scores[agent_name] = max(0.1, 1.0 + signal_bonus + pnl_score)

        leader = max(scores, key=scores.get)
        laggard = min(scores, key=scores.get)
        if leader == laggard:
            return {"star_agent": None, "lagging_agent": None, "shift_amount": 0.0, "reasoning": "Signal allocation is unchanged."}

        spread = scores[leader] - scores[laggard]
        if spread < 0.08:
            return {"star_agent": None, "lagging_agent": None, "shift_amount": 0.0, "reasoning": "Signal allocation is unchanged."}

        shift_amount = round(min(max(self.initial_cash * spread * 0.01, 100), self.agent_funds[laggard] * 0.12), 2)
        if shift_amount <= 0:
            return {"star_agent": None, "lagging_agent": None, "shift_amount": 0.0, "reasoning": "Signal allocation is unchanged."}

        return {
            "star_agent": leader,
            "lagging_agent": laggard,
            "shift_amount": shift_amount,
            "reasoning": f"Signal allocation moved ${shift_amount:.0f} from {laggard} to {leader} on conviction and live edge.",
        }

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
                )
            )
        items.sort(key=lambda item: item.market_value, reverse=True)
        return items

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

    def get_agent_allocations(self) -> List[Dict[str, Any]]:
        total_capital = self.get_total_value()
        snapshots = []
        for agent_name in self.agent_names:
            capital = self.agent_funds[agent_name] + self.get_agent_deployed_value(agent_name)
            if agent_name in self.paused_agents:
                status = "PAUSED"
            elif self.agent_cooldowns[agent_name] > self.tick:
                status = "COOLDOWN"
            else:
                status = "ACTIVE"
            snapshots.append(
                _dump_model(
                    AgentAllocation(
                        agent=agent_name,
                        capital=round(capital, 2),
                        cash=round(self.agent_funds[agent_name], 2),
                        deployed=round(self.get_agent_deployed_value(agent_name), 2),
                        realized_pnl=round(self.agent_realized_pnl[agent_name], 2),
                        unrealized_pnl=round(self.get_agent_unrealized_pnl(agent_name), 2),
                        share_pct=round(capital / total_capital, 4) if total_capital else 0.0,
                        last_decision=self.last_decisions[agent_name],
                        status=status,
                    )
                )
            )
        snapshots.sort(key=lambda item: item["capital"], reverse=True)
        return snapshots

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

    def get_news(self, live_items: Optional[List[Dict[str, Any]]] = None) -> List[str]:
        scenario_headlines = list(self.pending_headlines[:2])
        self.pending_headlines = self.pending_headlines[2:]
        scenario_items = self.build_news_items(scenario_headlines)

        if live_items:
            combined_items = [*scenario_items, *live_items][:8]
        else:
            sampled = random.sample(self.news_pool, 2)
            fallback_items = self.build_news_items(sampled)
            combined_items = [*scenario_items, *fallback_items][:4]

        self.latest_news_items = combined_items
        self.latest_news = [item["title"] for item in combined_items]
        return self.latest_news

    def build_news_items(self, headlines: List[str]) -> List[Dict[str, Any]]:
        positive_markers = ("cuts", "beat", "accelerating", "higher", "rip", "broadens", "bid")
        negative_markers = ("hotter", "pressure", "lower", "liquidations", "shock", "disruption", "flush")
        news_items = []
        for headline in headlines:
            lowered = headline.lower()
            assets = [asset for asset in self.prices if asset.lower() in lowered]
            if not assets and "ai" in lowered:
                assets = ["NVDA", "AMZN"]
            elif not assets and "crypto" in lowered:
                assets = ["BTC"]
            elif not assets and ("inflation" in lowered or "oil" in lowered):
                assets = ["AAPL", "AMZN", "TSLA"]

            sentiment = "neutral"
            if any(marker in lowered for marker in positive_markers):
                sentiment = "positive"
            elif any(marker in lowered for marker in negative_markers):
                sentiment = "negative"

            category = "macro"
            if "crypto" in lowered or "btc" in lowered:
                category = "crypto"
            elif "earnings" in lowered or "ai" in lowered or "tech" in lowered:
                category = "equities"
            elif "fed" in lowered or "inflation" in lowered or "rates" in lowered:
                category = "macro"

            base_impact = 0.38 + len(assets) * 0.08
            if sentiment != "neutral":
                base_impact += 0.14

            news_items.append(
                _dump_model(
                    NewsItem(
                        title=headline,
                        time=_now_hms(),
                        category=category,
                        sentiment=sentiment,
                        impact_score=round(_clamp(base_impact, 0.25, 0.95), 2),
                        assets=assets,
                    )
                )
            )
        return news_items

    def get_projected_total_value(self) -> float:
        current_value = self.get_total_value()
        if self.initial_cash <= 0:
            return current_value

        projected_edge = 0.0
        for agent_name, decision in self.latest_agent_signals.items():
            action = decision.get("action", "HOLD")
            asset = decision.get("asset")
            if action == "HOLD" or asset not in self.prices:
                continue

            expected_move = _parse_expected_move(str(decision.get("expected_move", "")))
            confidence = float(decision.get("confidence", 0.0) or 0.0)
            amount = float(decision.get("amount", 0.0) or 0.0)
            position = self.agent_positions[agent_name].get(asset, {})
            live_exposure = float(position.get("quantity", 0.0) or 0.0) * self.prices[asset]

            if action == "BUY":
                influence = max(live_exposure, amount)
                direction = 1.0
            else:
                influence = max(amount * 0.65, min(live_exposure, amount) if live_exposure else 0.0)
                direction = 0.55

            projected_edge += influence * expected_move * confidence * direction

        projected_edge = _clamp(projected_edge, -self.initial_cash * 0.12, self.initial_cash * 0.12)
        return round(max(current_value + projected_edge, 0.0), 2)

    def capture_projection(self) -> Dict[str, Any]:
        total_value = round(self.get_total_value(), 2)
        projected_total_value = self.get_projected_total_value()
        actual_pnl = round(total_value - self.initial_cash, 2)
        projected_pnl = round(projected_total_value - self.initial_cash, 2)
        point = _dump_model(
            ProjectionPoint(
                tick=self.tick,
                time=_now_hms(),
                total_value=total_value,
                actual_pnl=actual_pnl,
                projected_pnl=projected_pnl,
                projected_total_value=projected_total_value,
                total_return_pct=round(actual_pnl / self.initial_cash, 4) if self.initial_cash else 0.0,
                projected_return_pct=round(projected_pnl / self.initial_cash, 4) if self.initial_cash else 0.0,
            )
        )
        self.latest_projection = point
        self.projection_history = [*self.projection_history, point][-90:]
        return point

    def push_activity(
        self,
        kind: str,
        headline: str,
        message: str,
        tone: str = "neutral",
        agent: Optional[str] = None,
        target_agent: Optional[str] = None,
        asset: Optional[str] = None,
        amount: Optional[float] = None,
        confidence: Optional[float] = None,
    ) -> Dict[str, Any]:
        event = _dump_model(
            ActivityEvent(
                id=str(uuid.uuid4()),
                time=_now_hms(),
                kind=kind,
                headline=headline,
                message=message,
                tone=tone,
                agent=agent,
                target_agent=target_agent,
                asset=asset,
                amount=round(amount, 2) if amount is not None else None,
                confidence=round(confidence, 2) if confidence is not None else None,
            )
        )
        self.activity_log = [event, *self.activity_log][:80]
        return event

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

    def apply_trade_impact(self, trade: Trade):
        asset = trade.asset
        if asset not in self.prices:
            return

        previous_tick_price = self.previous_prices.get(asset, self.prices[asset])
        current_price = self.prices[asset]
        direction = 1.0 if trade.action == "BUY" else -1.0
        confidence = float(trade.confidence or 0.5)
        size_ratio = trade.amount / max(self.initial_cash, 1.0)
        impact = 0.0018 + confidence * 0.006 + min(size_ratio, 0.18) * 0.05 + random.uniform(0.0, 0.0015)
        impact = _clamp(impact, TRADE_IMPACT_MIN_PCT, TRADE_IMPACT_MAX_PCT)
        repriced = max(current_price * (1 + direction * impact), 1.0)

        self.prices[asset] = round(repriced, 2)
        changes = dict(self.latest_market_data.get("changes", {}))
        prices = dict(self.latest_market_data.get("prices", self.prices))
        prices[asset] = self.prices[asset]
        changes[asset] = round(_pct(self.prices[asset], previous_tick_price), 4)
        self.latest_market_data = {
            **self.latest_market_data,
            "prices": prices,
            "changes": changes,
        }

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


sim = MarketSim()
live_news_service = LiveNewsService()


async def _broadcast_core_state():
    await manager.broadcast({"type": "market_update", "data": sim.latest_market_data})
    await manager.broadcast({"type": "news_update", "data": sim.latest_news_items})
    await manager.broadcast({"type": "portfolio_update", "data": _dump_model(sim.get_portfolio_snapshot())})
    await manager.broadcast({"type": "benchmark_update", "data": sim.get_benchmark_payload()})
    await manager.broadcast({"type": "leaderboard_update", "data": sim.get_leaderboard()})
    await manager.broadcast({"type": "allocation_update", "data": sim.get_agent_allocations()})
    if sim.latest_projection is not None:
        await manager.broadcast({"type": "projection_update", "data": sim.latest_projection})
    await manager.broadcast({"type": "control_state", "data": sim.get_session_state()})


async def _broadcast_live_state():
    projection = sim.capture_projection()
    await manager.broadcast({"type": "portfolio_update", "data": _dump_model(sim.get_portfolio_snapshot())})
    await manager.broadcast({"type": "allocation_update", "data": sim.get_agent_allocations()})
    await manager.broadcast({"type": "projection_update", "data": projection})


async def trading_loop(duration: int):
    sim.session_active = True
    end_time = time.time() + duration
    sim.latest_news_items = sim.build_news_items(sim.latest_news)
    await _broadcast_core_state()

    while time.time() < end_time and sim.session_active:
        sim.tick += 1
        markets = sim.update_markets()
        await _broadcast_live_state()
        live_news = await asyncio.to_thread(live_news_service.fetch, sim.prices)
        news = sim.get_news(live_news)

        await manager.broadcast({"type": "scenario_update", "data": {"active_scenario": sim.active_scenario}})
        await manager.broadcast({"type": "market_update", "data": markets})
        await manager.broadcast({"type": "news_update", "data": sim.latest_news_items})
        for item in sim.latest_news_items:
            activity = sim.push_activity(
                kind="news",
                headline=item["category"].upper(),
                message=item["title"],
                tone="positive" if item["sentiment"] == "positive" else "negative" if item["sentiment"] == "negative" else "neutral",
                asset=item["assets"][0] if item["assets"] else None,
            )
            await manager.broadcast({"type": "activity_event", "data": activity})

        forced_trades = sim.enforce_stop_losses()
        for forced_trade in forced_trades:
            sim.trades.append(forced_trade)
            await manager.broadcast({"type": "trade_execution", "data": _dump_model(forced_trade)})
            await _broadcast_live_state()
            activity = sim.push_activity(
                kind="risk",
                headline="Stop-loss exit",
                message="{0} was forced out of {1} after a drawdown breach.".format(
                    forced_trade.agent, forced_trade.asset
                ),
                tone="negative",
                agent=forced_trade.agent,
                asset=forced_trade.asset,
                amount=forced_trade.amount,
                confidence=forced_trade.confidence,
            )
            await manager.broadcast({"type": "activity_event", "data": activity})
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
                    "message": "Committee is routing {0} fresh headlines, {1} open positions, and live treasury pressure.".format(
                        len(news), len(sim.get_portfolio_items())
                    )
                },
            }
        )

        agent_performance = {}
        agent_names = list(agents.keys())
        raw_decisions = await asyncio.gather(
            *[
                agents[agent_name].analyze(markets, news, portfolio_state, sim.agent_funds[agent_name])
                for agent_name in agent_names
            ]
        )
        for agent_name, decision in zip(agent_names, raw_decisions):
            decision, risk_messages = sim._risk_adjust_decision(agent_name, decision)
            sim.latest_agent_signals[agent_name] = dict(decision)
            committee_approved = True

            for message in risk_messages:
                activity = sim.push_activity(
                    kind="risk",
                    headline="Risk engine intervention",
                    message=message,
                    tone="negative",
                    agent=agent_name,
                    asset=decision.get("asset"),
                    amount=float(decision.get("amount", 0.0) or 0.0),
                    confidence=float(decision.get("confidence", 0.0) or 0.0),
                )
                await manager.broadcast({"type": "activity_event", "data": activity})
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
                judge_names = [judge_name for judge_name in agent_names if judge_name != agent_name]
                votes = await asyncio.gather(
                    *[agents[judge_name].judge(decision, news) for judge_name in judge_names]
                )
                for judge_name, vote_result in zip(judge_names, votes):
                    relay_activity = sim.push_activity(
                        kind="relay",
                        headline="{0} to {1}".format(judge_name, agent_name),
                        message="{0} {1} the {2} {3} ticket.".format(
                            judge_name,
                            "backs" if vote_result.get("vote") == "YES" else "pushes back on",
                            decision.get("action", "HOLD"),
                            decision.get("asset", "basket"),
                        ),
                        tone="positive" if vote_result.get("vote") == "YES" else "negative",
                        agent=judge_name,
                        target_agent=agent_name,
                        asset=decision.get("asset"),
                        amount=float(decision.get("amount", 0.0) or 0.0),
                        confidence=float(decision.get("confidence", 0.0) or 0.0),
                    )
                    await manager.broadcast({"type": "activity_event", "data": relay_activity})

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
                                for judge_name, vote in zip(judge_names, votes)
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
                    veto_activity = sim.push_activity(
                        kind="committee",
                        headline="Committee veto",
                        message="{0} lost committee approval on {1}.".format(agent_name, decision.get("asset")),
                        tone="negative",
                        agent=agent_name,
                        asset=decision.get("asset"),
                        confidence=float(decision.get("confidence", 0.0) or 0.0),
                    )
                    await manager.broadcast({"type": "activity_event", "data": veto_activity})
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
            reasoning_activity = sim.push_activity(
                kind="decision",
                headline="{0} {1} {2}".format(
                    agent_name,
                    decision.get("action", "HOLD"),
                    decision.get("asset", "watchlist"),
                ),
                message=decision.get("reasoning", "No reasoning provided."),
                tone="positive" if decision.get("action") == "BUY" else "negative" if decision.get("action") == "SELL" else "neutral",
                agent=agent_name,
                asset=decision.get("asset"),
                amount=float(decision.get("amount", 0.0) or 0.0),
                confidence=float(decision.get("confidence", 0.0) or 0.0),
            )
            await manager.broadcast({"type": "activity_event", "data": reasoning_activity})

            trade = sim.update_portfolio(agent_name, decision, committee_approved)
            if trade is not None:
                sim.apply_trade_impact(trade)
                sim.trades.append(trade)
                await manager.broadcast({"type": "market_update", "data": sim.latest_market_data})
                await manager.broadcast({"type": "trade_execution", "data": _dump_model(trade)})
                await _broadcast_live_state()
                trade_activity = sim.push_activity(
                    kind="trade",
                    headline="{0} executed {1} {2}".format(agent_name, trade.action, trade.asset),
                    message="{0} routed {1} at {2} with {3:.0f}% confidence.".format(
                        agent_name,
                        format(trade.amount, ".2f"),
                        format(trade.price, ".2f"),
                        trade.confidence * 100,
                    ),
                    tone="positive" if trade.action == "BUY" else "neutral",
                    agent=agent_name,
                    asset=trade.asset,
                    amount=trade.amount,
                    confidence=trade.confidence,
                )
                await manager.broadcast({"type": "activity_event", "data": trade_activity})

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

        treasury_moves = [
            await governor.reallocate(agent_performance),
            sim.get_dynamic_allocation_shift(agent_performance),
        ]
        for reallocation in treasury_moves:
            star_agent = reallocation.get("star_agent")
            lagging_agent = reallocation.get("lagging_agent")
            shift_amount = float(reallocation.get("shift_amount", 0) or 0)
            if not (star_agent and lagging_agent and shift_amount > 0):
                continue
            shift_amount = min(shift_amount, sim.agent_funds[lagging_agent])
            if shift_amount <= 0:
                continue
            sim.agent_funds[lagging_agent] -= shift_amount
            sim.agent_funds[star_agent] += shift_amount
            treasury_activity = sim.push_activity(
                kind="treasury",
                headline="Treasury reallocation",
                message=reallocation.get("reasoning"),
                tone="positive",
                agent=star_agent,
                target_agent=lagging_agent,
                amount=shift_amount,
            )
            await manager.broadcast({"type": "activity_event", "data": treasury_activity})
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
            await _broadcast_live_state()

        if sim.should_trigger_kill_switch():
            sim.override_active = True
            kill_switch_activity = sim.push_activity(
                kind="risk",
                headline="Kill switch engaged",
                message="Autonomous execution is paused after the drawdown threshold was breached.",
                tone="negative",
            )
            await manager.broadcast({"type": "activity_event", "data": kill_switch_activity})
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
        await manager.broadcast({"type": "leaderboard_update", "data": sim.get_leaderboard()})
        await _broadcast_live_state()
        await manager.broadcast({"type": "control_state", "data": sim.get_session_state()})

        await asyncio.sleep(TICK_DELAY_SECONDS)

    sim.session_active = False
    sim.active_scenario = None
    summary = sim.generate_summary()
    await manager.broadcast({"type": "session_summary", "data": summary})
    await manager.broadcast({"type": "session_end", "data": summary})
