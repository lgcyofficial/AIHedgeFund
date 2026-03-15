import asyncio
import json
import os
import random
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
MODEL_TIMEOUT_SECONDS = float(os.getenv("MODEL_TIMEOUT_SECONDS", "1.5"))

try:
    genai = __import__("google.generativeai", fromlist=["unused"]) if api_key else None
except Exception:  # pragma: no cover - optional dependency at runtime
    genai = None

SYSTEM_PROMPT = """You are an AI hedge fund trading agent.
Return strict JSON with keys:
- asset
- action
- amount
- confidence
- reasoning
- thesis
- catalyst
- expected_move
"""

AI_ASSETS = ["NVDA", "AAPL", "BTC", "TSLA", "AMZN"]

ASSET_THEMES = {
    "NVDA": ["AI infrastructure demand", "chip demand acceleration", "semis momentum"],
    "AAPL": ["consumer resilience", "device refresh cycle", "services margin support"],
    "BTC": ["macro liquidity", "risk-on rotation", "crypto beta"],
    "TSLA": ["EV delivery expectations", "high-beta momentum", "autonomy speculation"],
    "AMZN": ["cloud resilience", "retail operating leverage", "AI capex narrative"],
}

POSITIVE_KEYWORDS = {
    "AI": ["NVDA", "AMZN"],
    "Tech": ["NVDA", "AAPL", "AMZN", "TSLA"],
    "Crypto": ["BTC"],
    "Fed": ["AAPL", "AMZN", "BTC"],
    "rate cuts": ["AAPL", "AMZN", "BTC", "TSLA"],
    "growth": ["NVDA", "TSLA", "AMZN"],
}

NEGATIVE_KEYWORDS = {
    "Inflation": ["TSLA", "AMZN", "AAPL", "BTC"],
    "supply shock": ["AMZN", "TSLA"],
    "volatile": ["BTC", "TSLA"],
    "hotter": ["BTC", "TSLA", "AAPL"],
}


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _extract_json(text: str) -> Dict[str, Any]:
    cleaned = text.strip()
    if "```json" in cleaned:
        cleaned = cleaned.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in cleaned:
        cleaned = cleaned.split("```", 1)[1].split("```", 1)[0].strip()
    return json.loads(cleaned)


class Agent:
    def __init__(self, name: str, strategy: str):
        self.name = name
        self.strategy = strategy
        self.model = None

        if api_key and genai is not None:
            genai.configure(api_key=api_key)
            self.model = genai.GenerativeModel(
                "gemini-2.0-flash",
                system_instruction=SYSTEM_PROMPT,
            )

    async def analyze(
        self,
        market_data: Dict[str, Any],
        news: List[str],
        portfolio: Dict[str, Any],
        capital: float,
    ) -> Dict[str, Any]:
        if self.model is not None:
            llm_decision = await self._try_model_decision(market_data, news, portfolio, capital)
            if llm_decision is not None:
                return llm_decision
        return self._heuristic_decision(market_data, news, capital)

    async def judge(self, proposal: Dict[str, Any], news: List[str]) -> Dict[str, Any]:
        if self.model is not None:
            llm_vote = await self._try_model_vote(proposal, news)
            if llm_vote is not None:
                return llm_vote
        return self._heuristic_vote(proposal, news)

    async def _try_model_decision(
        self,
        market_data: Dict[str, Any],
        news: List[str],
        portfolio: Dict[str, Any],
        capital: float,
    ) -> Optional[Dict[str, Any]]:
        prompt = f"""
Agent Strategy: {self.strategy}
Available Capital: ${capital:.2f}
Current Portfolio: {json.dumps(portfolio)}
Market Data: {json.dumps(market_data)}
Recent News: {json.dumps(news)}

Return one JSON object only.
"""
        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(lambda: self.model.generate_content(prompt)),
                timeout=MODEL_TIMEOUT_SECONDS,
            )
            parsed = _extract_json(response.text)
            return self._normalize_decision(parsed, capital)
        except Exception:
            return None

    async def _try_model_vote(self, proposal: Dict[str, Any], news: List[str]) -> Optional[Dict[str, Any]]:
        prompt = f"""
Agent Strategy: {self.strategy}
Trade Proposal: {json.dumps(proposal)}
Current News: {json.dumps(news)}

Return JSON with keys vote and reasoning only.
"""
        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(lambda: self.model.generate_content(prompt)),
                timeout=MODEL_TIMEOUT_SECONDS,
            )
            parsed = _extract_json(response.text)
            vote = parsed.get("vote", "NO")
            return {
                "vote": "YES" if str(vote).upper() == "YES" else "NO",
                "reasoning": str(parsed.get("reasoning", "No decisive edge."))[:160],
            }
        except Exception:
            return None

    def _normalize_decision(self, decision: Dict[str, Any], capital: float) -> Dict[str, Any]:
        asset = str(decision.get("asset", "NVDA")).upper()
        if asset not in AI_ASSETS:
            asset = "NVDA"

        action = str(decision.get("action", "HOLD")).upper()
        if action not in {"BUY", "SELL", "HOLD"}:
            action = "HOLD"

        amount = _clamp(float(decision.get("amount", 0) or 0), 0, capital)
        confidence = _clamp(float(decision.get("confidence", 0.5) or 0.5), 0.05, 0.99)

        return {
            "asset": asset,
            "action": action,
            "amount": amount,
            "confidence": confidence,
            "reasoning": str(decision.get("reasoning", "Monitoring setup for a cleaner entry."))[:180],
            "thesis": str(decision.get("thesis", "Relative strength is driving the setup."))[:140],
            "catalyst": str(decision.get("catalyst", "Market regime rotation."))[:120],
            "expected_move": str(decision.get("expected_move", "2-4%"))[:40],
        }

    def _heuristic_decision(self, market_data: Dict[str, Any], news: List[str], capital: float) -> Dict[str, Any]:
        scores = {asset: 0.0 for asset in AI_ASSETS}
        changes = market_data.get("changes", {})

        for asset, change in changes.items():
            if asset in scores:
                scores[asset] += float(change) * 8

        joined_news = " | ".join(news)
        for keyword, assets in POSITIVE_KEYWORDS.items():
            if keyword.lower() in joined_news.lower():
                for asset in assets:
                    scores[asset] += 0.35

        for keyword, assets in NEGATIVE_KEYWORDS.items():
            if keyword.lower() in joined_news.lower():
                for asset in assets:
                    scores[asset] -= 0.35

        if "Momentum" in self.name:
            for asset, change in changes.items():
                scores[asset] += float(change) * 10
        elif "News" in self.name:
            for keyword, assets in POSITIVE_KEYWORDS.items():
                if keyword.lower() in joined_news.lower():
                    for asset in assets:
                        scores[asset] += 0.4
        elif "Macro" in self.name:
            scores["AAPL"] += 0.15
            scores["AMZN"] += 0.15
            scores["BTC"] -= 0.05
        elif "Volatility" in self.name:
            for asset, change in changes.items():
                scores[asset] += abs(float(change)) * 9

        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        best_asset, best_score = ranked[0]
        worst_asset, worst_score = ranked[-1]

        if capital <= 0:
            return {
                "asset": best_asset,
                "action": "HOLD",
                "amount": 0,
                "confidence": 0.25,
                "reasoning": "No deployable capital remains.",
                "thesis": "Capital preservation.",
                "catalyst": "Treasury constraints.",
                "expected_move": "flat",
            }

        if best_score < 0.15 and worst_score > -0.2:
            return {
                "asset": best_asset,
                "action": "HOLD",
                "amount": 0,
                "confidence": 0.33,
                "reasoning": "Signal quality is mixed, so patience is higher EV than forcing a trade.",
                "thesis": "No clean edge.",
                "catalyst": "Cross-currents in tape and headlines.",
                "expected_move": "flat",
            }

        bullish = best_score >= abs(worst_score)
        asset = best_asset if bullish else worst_asset
        action = "BUY" if bullish else "SELL"
        confidence = _clamp(0.45 + abs(best_score if bullish else worst_score) * 0.18, 0.35, 0.9)
        size_fraction = 0.16 + (confidence - 0.35) * 0.6
        amount = round(capital * _clamp(size_fraction, 0.08, 0.4), 2)
        theme = random.choice(ASSET_THEMES.get(asset, ["regime shift"]))

        direction_text = "breakout continuation" if action == "BUY" else "fade setup"
        return {
            "asset": asset,
            "action": action,
            "amount": amount,
            "confidence": round(confidence, 2),
            "reasoning": f"{asset} has the cleanest {direction_text} versus the rest of the board.",
            "thesis": f"{theme} is the highest-conviction expression of this agent's mandate.",
            "catalyst": " + ".join(news[:2])[:120] if news else "price regime shift",
            "expected_move": f"{2 + int(confidence * 4)}-{4 + int(confidence * 5)}%",
        }

    def _heuristic_vote(self, proposal: Dict[str, Any], news: List[str]) -> Dict[str, Any]:
        action = proposal.get("action", "HOLD")
        confidence = float(proposal.get("confidence", 0.5))
        amount = float(proposal.get("amount", 0))
        asset = proposal.get("asset", "NVDA")
        joined_news = " ".join(news).lower()

        approval_score = confidence
        if amount > 1800:
            approval_score -= 0.15
        if action == "SELL":
            approval_score -= 0.05
        if asset == "BTC" and "volatile" in joined_news:
            approval_score -= 0.1
        if "rate cuts" in joined_news and asset in {"AMZN", "AAPL", "BTC"}:
            approval_score += 0.08

        vote = "YES" if approval_score >= 0.5 else "NO"
        reasoning = (
            "Position size is justified by conviction and market regime."
            if vote == "YES"
            else "Edge is too weak relative to size and current headline risk."
        )
        return {"vote": vote, "reasoning": reasoning}


class Governor(Agent):
    def __init__(self):
        super().__init__(
            "Treasury Governor",
            "You reallocate capital toward agents with the best realized edge and discipline.",
        )

    async def reallocate(self, agent_stats: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        ranked = sorted(
            agent_stats.items(),
            key=lambda item: (
                item[1].get("realized_pnl", 0) + item[1].get("unrealized_pnl", 0),
                item[1].get("win_rate", 0),
            ),
            reverse=True,
        )

        if len(ranked) < 2:
            return {
                "star_agent": None,
                "lagging_agent": None,
                "shift_amount": 0,
                "reasoning": "Insufficient data to rebalance treasury.",
            }

        star_agent, star_stats = ranked[0]
        lagging_agent, lagging_stats = ranked[-1]
        edge = (
            star_stats.get("realized_pnl", 0)
            + star_stats.get("unrealized_pnl", 0)
            - lagging_stats.get("realized_pnl", 0)
            - lagging_stats.get("unrealized_pnl", 0)
        )

        if edge <= 0:
            return {
                "star_agent": None,
                "lagging_agent": None,
                "shift_amount": 0,
                "reasoning": "No agent has earned incremental capital yet.",
            }

        shift_amount = round(min(max(edge * 0.2, 150), lagging_stats.get("balance", 0) * 0.2), 2)
        if shift_amount <= 0:
            return {
                "star_agent": None,
                "lagging_agent": None,
                "shift_amount": 0,
                "reasoning": "Treasury remains unchanged while balances are constrained.",
            }

        return {
            "star_agent": star_agent,
            "lagging_agent": lagging_agent,
            "shift_amount": shift_amount,
            "reasoning": f"Redirecting ${shift_amount:.0f} from {lagging_agent} to {star_agent} based on edge persistence.",
        }


agents = {
    "Momentum": Agent(
        "Momentum Agent",
        "Trade price continuation and trend persistence. Prefer decisive breakouts and avoid chop.",
    ),
    "News": Agent(
        "News Agent",
        "Exploit catalysts and headline sentiment. React faster than the broader committee.",
    ),
    "Macro": Agent(
        "Macro Agent",
        "Prefer stable compounders and macro-consistent risk positioning.",
    ),
    "Volatility": Agent(
        "Volatility Agent",
        "Monetize sharp moves, event risk, and regime shifts. Stay inactive if dispersion is low.",
    ),
}

governor = Governor()
