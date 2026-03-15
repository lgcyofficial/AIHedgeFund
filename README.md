# TradeAgent

We built an AI-native hedge fund simulator that thinks like a team, acts like a fund, and explains itself like a product.

TradeAgent is an AI-native hedge fund simulator for live decision making, portfolio construction, and real-time investment intelligence.

The problem is not lack of ideas. The problem is turning ideas into coordinated, risk-aware portfolio decisions fast enough to matter.

Instead of asking one model to pick a stock, TradeAgent runs an entire fund workflow:

- agents propose trades
- a committee votes on large positions
- the treasury reallocates capital
- the research desk classifies the regime
- the portfolio-construction layer trims crowding
- the dashboard explains every move in real time

It combines a multi-agent trading committee, a portfolio-construction overlay, a research desk, factor and theme exposure models, benchmark tracking, and a backtest lab inside one command deck.

## Why This Lands Immediately

TradeAgent is compelling because it treats AI as an operating system for investment decisions, not as a single recommendation engine.

The product captures the full workflow that real teams care about. Specialized agents generate ideas from different perspectives. Large trades are challenged through committee voting before capital is deployed. Risk controls and portfolio-construction rules shape what actually gets executed. A research desk interprets the regime, and the dashboard makes the entire process visible through reasoning, exposures, benchmarks, and backtests.

That combination matters because it turns AI output into something structured, auditable, and useful. Instead of showing one answer, TradeAgent shows how a decision is formed, how it is challenged, how it is risk-managed, and how it is evaluated afterward.

It also demos extremely well. A user can inject a market event, watch the research brief update, see agents propose trades, observe the committee vote, and then watch the portfolio-construction layer rebalance the book in real time. That sequence makes the product easy to understand quickly while still showing real technical depth.

The result is a system that feels less like a prototype generating outputs and more like a product managing decisions.

## Why This Could Be Real

TradeAgent is built around workflows that already exist inside real investment teams:

- `research desks` frame market regime and risk
- `portfolio managers` decide where to allocate capital
- `risk teams` cap crowding and stop losses
- `investment committees` challenge large decisions
- `performance teams` compare results to benchmarks and historical regimes

The product makes that workflow visible and interactive.

That is why the idea feels tangible beyond a hackathon:

- it can be used as an internal PM/research/risk prototype
- it can serve as a training and simulation tool for discretionary teams
- it can evolve into an AI co-pilot for live portfolio review and scenario planning
- it already organizes outputs in a form that a real desk would recognize

## Why It Stands Out

Most AI trading demos stop at “the model picked a stock.”

TradeAgent goes further:

- `decision layer`
  Multiple specialized agents reason about the same market from different angles

- `control layer`
  Risk and portfolio construction actively shape what gets executed

- `explanation layer`
  The UI shows the chain of reasoning, votes, trims, benchmarks, factors, and research context

- `evaluation layer`
  The system can be judged against passive benchmarks and scenario backtests, not just a single flashy run

The result is a system that looks like a product someone could actually use to inspect, challenge, and improve investment decisions.

## What We Built

TradeAgent is a simulated autonomous fund with three layers:

1. `Decision Layer`
   Multiple AI trading agents generate trade proposals from market moves, news flow, and current portfolio state.

2. `Risk + Construction Layer`
   The system applies confidence gates, position caps, theme crowding limits, stop-loss rules, committee voting for large trades, treasury reallocation, and portfolio-construction trims.

3. `Intelligence + Presentation Layer`
   A live dashboard shows reasoning, benchmark performance, theme and factor exposures, research briefs, backtest results, risk alerts, and executed trades.

## What Makes It Valuable

TradeAgent is valuable because it shows what a real institutional workflow needs:

- `Multiple specialized agents`, not one monolithic model
- `Risk controls`, not blind automation
- `Portfolio construction`, not isolated trade ideas
- `Research context`, not unexplained actions
- `Benchmarking and backtests`, not vanity PnL
- `Live visibility`, so users can audit decisions as they happen

That makes the product useful as:

- a hackathon demo with clear product depth
- an internal PM/research/risk prototype
- a foundation for a more serious autonomous investing platform

It also lands well in a hackathon setting because it scores on the things judges usually reward:

- `Originality`
  Multi-agent fund orchestration is more ambitious and differentiated than a single chatbot wrapper.

- `Execution quality`
  The product has a live UI, backend architecture, event streaming, and multiple working subsystems.

- `Clarity`
  The reasoning, votes, risk events, and exposure maps make the system easy to understand quickly.

- `Usefulness`
  Even as a simulation, it models real workflows from hedge funds, trading desks, and portfolio management.

## Feature Comparison

What many AI finance demos show:

- one model
- one recommendation
- one chart
- little or no risk logic
- little explanation after the decision

What TradeAgent shows:

- multiple specialized agents
- committee approval on large trades
- research-driven regime interpretation
- portfolio construction and crowding control
- factor and theme decomposition
- benchmark comparison
- backtest evidence
- a live command deck that makes the whole process legible

## Core Features

- `Multi-agent committee`
  Momentum, News, Macro, and Volatility agents generate proposals.

- `Investment committee voting`
  Large trades are voted on by the other agents before execution.

- `Treasury governor`
  Capital is reallocated toward the best-performing agents.

- `Portfolio construction overlay`
  The fund actively manages crowding and trims overconcentrated sleeves.

- `Theme exposure map`
  Portfolio exposure is decomposed into thematic sleeves such as AI Infra, Consumer Tech, and Crypto Beta.

- `Factor exposure model`
  The book is also decomposed into style and risk factors such as Growth, Momentum, Quality, Beta, Low Vol, and Macro Liquidity.

- `Research desk`
  A research agent produces a live regime brief, watchlist, opportunities, and warnings.

- `Backtest lab`
  The system runs a scenario/risk-mandate matrix and reports alpha, drawdown, beat rate, and best run.

- `Scenario injection`
  Users can trigger event shocks like Fed Pivot, NVDA Earnings Beat, Crypto Flush, and Oil Shock.

- `Risk radar`
  The UI surfaces stop-losses, vetoes, kill-switch events, and construction trims in real time.

- `Benchmark race`
  The portfolio is tracked against passive benchmarks such as SPY, QQQ, and BTC.

## How It Works

### 1. Market Simulation

The backend simulates:

- asset prices
- benchmark prices
- headline/news flow
- scenario shocks

Each tick updates the market state and broadcasts it to the frontend.

### 2. Agent Decision Process

Each trading agent evaluates:

- current market changes
- active headlines
- portfolio state
- available capital

The agent returns:

- asset
- action
- amount
- confidence
- reasoning
- thesis
- catalyst
- expected move

If Gemini is available, the system can use it. If not, or if it times out, TradeAgent falls back to deterministic heuristics so the app remains responsive.

### 3. Risk and Construction Controls

Before execution, the system applies:

- confidence minimums
- max trade size
- max position size
- max theme exposure
- cooldown logic after losses
- stop-loss enforcement
- committee vote thresholds
- global kill-switch behavior

After agent execution, the portfolio-construction layer can trim overexposed themes to rebalance the book.

### 4. Research and Attribution

A research agent interprets the current tape and produces:

- market regime
- summary
- primary risk
- opportunities
- warnings
- watchlist

At the same time, the portfolio is decomposed into:

- theme exposures
- factor exposures
- construction status

### 5. Frontend Command Deck

The Next.js frontend renders:

- benchmark chart
- committee vote board
- reasoning stream
- scenario controls
- risk radar
- theme exposure map
- factor exposure model
- backtest lab
- research desk
- execution ledger
- portfolio snapshot

## Architecture

### Backend

- `FastAPI`
- `WebSocket` event streaming
- simulation engine for trading, risk, research, and backtests

Important files:

- [backend/main.py](/Users/vincerusso/Documents/GitHub/AIHedgeFund/backend/main.py)
- [backend/trading_loop.py](/Users/vincerusso/Documents/GitHub/AIHedgeFund/backend/trading_loop.py)
- [backend/agents.py](/Users/vincerusso/Documents/GitHub/AIHedgeFund/backend/agents.py)
- [backend/models.py](/Users/vincerusso/Documents/GitHub/AIHedgeFund/backend/models.py)

### Frontend

- `Next.js`
- `React`
- `TypeScript`
- `Tailwind CSS`

Important files:

- [frontend/src/components/Dashboard.tsx](/Users/vincerusso/Documents/GitHub/AIHedgeFund/frontend/src/components/Dashboard.tsx)
- [frontend/src/hooks/useWebSocket.ts](/Users/vincerusso/Documents/GitHub/AIHedgeFund/frontend/src/hooks/useWebSocket.ts)
- [frontend/src/types/index.ts](/Users/vincerusso/Documents/GitHub/AIHedgeFund/frontend/src/types/index.ts)

## API Overview

### Core session routes

- `POST /trade/start`
- `GET /portfolio`
- `GET /trades`
- `GET /state`

### Intelligence routes

- `GET /research`
- `GET /backtests/lab`
- `GET /benchmarks`
- `GET /scenarios`

### Control routes

- `POST /scenario/apply`
- `POST /control/override`
- `POST /control/agent`

### Streaming

- `WS /ws/stream`

## Quick Start

### Backend

From `backend/`:

```bash
./venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

Notes:

- The app works without Gemini by using heuristic fallbacks.
- If you use Gemini, put `GEMINI_API_KEY` in `backend/.env`.
- `backend/.env` is ignored by Git.

### Frontend

From `frontend/`:

```bash
npm install
npm run dev
```

Then open the local Next.js app in your browser.

## Demo Flow

If you are presenting this live:

1. Start with the benchmark race and explain the system at a high level.
2. Trigger a scenario like `NVDA Earnings Beat` or `Crypto Flush`.
3. Show the research desk updating the market regime.
4. Let the agents propose trades and show the committee vote panel.
5. Highlight the theme and factor exposure maps.
6. Point out the portfolio-construction layer trimming crowding.
7. Finish with the backtest lab and explain why the strategy is not just making random trades.

## Validation

The project has been verified with:

- backend Python syntax checks
- frontend lint
- frontend production build
- backend runtime checks for:
  - portfolio output
  - factor exposure output
  - backtest lab output
  - research brief output
  - short-session execution

## Security Notes

- `backend/.env` is ignored by Git
- local logs and virtualenv files are ignored
- Gemini calls are timeout-protected so the app falls back instead of hanging

## Current Limitations

- market data and backtests are simulated rather than historical market replays
- Gemini integration uses a deprecated SDK in the current environment
- the backend environment is still on Python 3.9, which produces warning noise

## What Makes This Special

TradeAgent is not just “AI picks a stock.”

It is a full-stack demonstration of:

- agentic decision making
- risk-aware automation
- portfolio construction
- research generation
- live interpretability
- benchmarked performance evaluation

That combination is what makes it feel closer to a real AI hedge fund product than a typical single-model trading demo.
