"use client";

import { useEffect, useRef, useState } from "react";

import {
  AgentLeaderboardEntry,
  AgentReasoning,
  BacktestLab,
  BenchmarkState,
  CommitteeVoteEvent,
  ControlState,
  MarketState,
  NewsItem,
  PortfolioState,
  PortfolioConstructionState,
  ResearchBrief,
  RiskEvent,
  ScenarioDefinition,
  SessionSummary,
  Trade,
  WebSocketMessage,
} from "../types";

const API_BASE = "http://127.0.0.1:8000";

type HistoryPoint = {
  time: number;
  fund: number;
  benchmarks: Record<string, number>;
};

const defaultControlState: ControlState = {
  session_active: false,
  risk: "medium",
  override_active: false,
  paused_agents: [],
  active_scenario: null,
};

const defaultConstructionState: PortfolioConstructionState = {
  status: "balanced",
  dominant_theme: null,
  cash_buffer_weight: 1,
  concentration_score: 0,
  actions: [],
  notes: [],
};

const defaultResearchBrief: ResearchBrief = {
  regime: "Awaiting Session",
  summary: "The research desk will characterize the tape once the market opens.",
  primary_risk: "No active session.",
  opportunities: [],
  warnings: [],
  watchlist: [],
};

export function useWebSocket(url: string) {
  const [isConnected, setIsConnected] = useState(false);
  const [portfolio, setPortfolio] = useState<PortfolioState | null>(null);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [reasonings, setReasonings] = useState<AgentReasoning[]>([]);
  const [news, setNews] = useState<NewsItem[]>([]);
  const [marketData, setMarketData] = useState<MarketState>({ prices: {}, changes: {} });
  const [sessionActive, setSessionActive] = useState(false);
  const [coordination, setCoordination] = useState("");
  const [benchmarkState, setBenchmarkState] = useState<BenchmarkState>({ values: {}, returns: {} });
  const [benchmarkHistory, setBenchmarkHistory] = useState<HistoryPoint[]>([]);
  const [committeeVotes, setCommitteeVotes] = useState<CommitteeVoteEvent[]>([]);
  const [leaderboard, setLeaderboard] = useState<AgentLeaderboardEntry[]>([]);
  const [riskEvents, setRiskEvents] = useState<RiskEvent[]>([]);
  const [constructionState, setConstructionState] = useState<PortfolioConstructionState>(defaultConstructionState);
  const [researchBrief, setResearchBrief] = useState<ResearchBrief>(defaultResearchBrief);
  const [backtestLab, setBacktestLab] = useState<BacktestLab | null>(null);
  const [controlState, setControlState] = useState<ControlState>(defaultControlState);
  const [scenarios, setScenarios] = useState<ScenarioDefinition[]>([]);
  const [sessionSummary, setSessionSummary] = useState<SessionSummary | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<number | null>(null);
  const benchmarkRef = useRef<BenchmarkState>({ values: {}, returns: {} });

  useEffect(() => {
    const loadBootstrap = async () => {
      try {
        const [scenarioRes, stateRes, tradeRes, boardRes, benchmarkRes, researchRes, backtestRes] = await Promise.all([
          fetch(`${API_BASE}/scenarios`),
          fetch(`${API_BASE}/state`),
          fetch(`${API_BASE}/trades`),
          fetch(`${API_BASE}/agents/leaderboard`),
          fetch(`${API_BASE}/benchmarks`),
          fetch(`${API_BASE}/research`),
          fetch(`${API_BASE}/backtests/lab`),
        ]);

        if (scenarioRes.ok) {
          setScenarios(await scenarioRes.json());
        }
        if (stateRes.ok) {
          const state: ControlState = await stateRes.json();
          setControlState(state);
          setSessionActive(state.session_active);
        }
        if (tradeRes.ok) {
          setTrades((await tradeRes.json()).slice(0, 50));
        }
        if (boardRes.ok) {
          setLeaderboard(await boardRes.json());
        }
        if (benchmarkRes.ok) {
          setBenchmarkState(await benchmarkRes.json());
        }
        if (researchRes.ok) {
          setResearchBrief(await researchRes.json());
        }
        if (backtestRes.ok) {
          setBacktestLab(await backtestRes.json());
        }
      } catch (error) {
        console.error("Bootstrap fetch failed", error);
      }
    };

    loadBootstrap();
  }, []);

  useEffect(() => {
    let mounted = true;

    const connect = () => {
      if (!mounted || wsRef.current?.readyState === WebSocket.OPEN) {
        return;
      }

      const ws = new WebSocket(url);

      ws.onopen = () => {
        if (!mounted) {
          return;
        }
        setIsConnected(true);
      };

      ws.onclose = () => {
        if (!mounted) {
          return;
        }
        setIsConnected(false);
        if (reconnectTimerRef.current) {
          window.clearTimeout(reconnectTimerRef.current);
        }
        reconnectTimerRef.current = window.setTimeout(connect, 1200);
      };

      ws.onmessage = (event) => {
        try {
          const msg: WebSocketMessage = JSON.parse(event.data);

          switch (msg.type) {
            case "portfolio_update":
              setPortfolio(msg.data);
              setConstructionState(msg.data.construction);
              setBenchmarkHistory((history) =>
                [
                  ...history,
                  {
                    time: Date.now(),
                    fund: msg.data.total_value,
                    benchmarks: benchmarkRef.current.values,
                  },
                ].slice(-60),
              );
              break;
            case "trade_execution":
              setTrades((prev) => [msg.data, ...prev].slice(0, 50));
              break;
            case "agent_reasoning":
              setReasonings((prev) => [msg.data, ...prev].slice(0, 24));
              break;
            case "agent_coordination":
              setCoordination(msg.data.message);
              break;
            case "market_update":
              setMarketData(msg.data);
              break;
            case "news_update":
              setNews((prev) => [...msg.data, ...prev].slice(0, 20));
              break;
            case "treasury_update":
              setPortfolio((prev) => (prev ? { ...prev, allocations: msg.data.allocations } : prev));
              setCoordination(msg.data.message);
              break;
            case "committee_vote":
              setCommitteeVotes((prev) => [msg.data, ...prev].slice(0, 8));
              break;
            case "benchmark_update":
              benchmarkRef.current = msg.data;
              setBenchmarkState(msg.data);
              break;
            case "leaderboard_update":
              setLeaderboard(msg.data);
              break;
            case "risk_event":
              setRiskEvents((prev) => [msg.data, ...prev].slice(0, 12));
              break;
            case "control_state":
              setControlState(msg.data);
              setSessionActive(msg.data.session_active);
              break;
            case "portfolio_construction":
              setConstructionState(msg.data);
              setPortfolio((prev) => (prev ? { ...prev, construction: msg.data } : prev));
              break;
            case "research_update":
              setResearchBrief(msg.data);
              break;
            case "scenario_update":
              setControlState((prev) => ({ ...prev, active_scenario: msg.data.active_scenario }));
              break;
            case "session_summary":
            case "session_end":
              setSessionActive(false);
              setSessionSummary(msg.data);
              break;
          }
        } catch (error) {
          console.error("Error parsing WS message", error);
        }
      };

      wsRef.current = ws;
    };

    connect();

    return () => {
      mounted = false;
      if (reconnectTimerRef.current) {
        window.clearTimeout(reconnectTimerRef.current);
      }
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [url]);

  const startSession = async (capital: number, risk: string, duration: number, scenario?: string) => {
    setTrades([]);
    setReasonings([]);
    setNews([]);
    setCommitteeVotes([]);
    setRiskEvents([]);
    setBenchmarkHistory([]);
    setSessionSummary(null);

    const response = await fetch(`${API_BASE}/trade/start`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ capital, risk, duration, scenario: scenario || null }),
    });

    if (!response.ok) {
      throw new Error("Failed to start session");
    }

    setSessionActive(true);
  };

  const applyScenario = async (scenario: string) => {
    const response = await fetch(`${API_BASE}/scenario/apply`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scenario }),
    });

    if (!response.ok) {
      throw new Error("Failed to apply scenario");
    }
  };

  const setOverride = async (enabled: boolean) => {
    const response = await fetch(`${API_BASE}/control/override`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled }),
    });

    if (!response.ok) {
      throw new Error("Failed to update override");
    }

    const nextState = await response.json();
    setControlState((prev) => ({ ...prev, override_active: nextState.override_active }));
  };

  const setAgentPaused = async (agent: string, paused: boolean) => {
    const response = await fetch(`${API_BASE}/control/agent`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ agent, paused }),
    });

    if (!response.ok) {
      throw new Error("Failed to update agent control");
    }
  };

  return {
    isConnected,
    portfolio,
    trades,
    reasonings,
    news,
    marketData,
    sessionActive,
    coordination,
    benchmarkState,
    benchmarkHistory,
    committeeVotes,
    leaderboard,
    riskEvents,
    constructionState,
    researchBrief,
    backtestLab,
    controlState,
    scenarios,
    sessionSummary,
    startSession,
    applyScenario,
    setOverride,
    setAgentPaused,
  };
}
