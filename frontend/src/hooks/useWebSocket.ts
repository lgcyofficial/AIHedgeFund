"use client";

import { useEffect, useRef, useState } from "react";

import {
  ActivityEvent,
  AgentAllocation,
  AgentLeaderboardEntry,
  AgentReasoning,
  BenchmarkState,
  CommitteeVoteEvent,
  ControlState,
  MarketState,
  NewsItem,
  PortfolioState,
  ProjectionPoint,
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
  const [allocations, setAllocations] = useState<AgentAllocation[]>([]);
  const [projectionHistory, setProjectionHistory] = useState<ProjectionPoint[]>([]);
  const [latestProjection, setLatestProjection] = useState<ProjectionPoint | null>(null);
  const [activity, setActivity] = useState<ActivityEvent[]>([]);
  const [riskEvents, setRiskEvents] = useState<RiskEvent[]>([]);
  const [controlState, setControlState] = useState<ControlState>(defaultControlState);
  const [scenarios, setScenarios] = useState<ScenarioDefinition[]>([]);
  const [sessionSummary, setSessionSummary] = useState<SessionSummary | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<number | null>(null);
  const benchmarkRef = useRef<BenchmarkState>({ values: {}, returns: {} });

  const clearLiveState = () => {
    setPortfolio(null);
    setTrades([]);
    setReasonings([]);
    setNews([]);
    setMarketData({ prices: {}, changes: {} });
    setCoordination("");
    setCommitteeVotes([]);
    setAllocations([]);
    setProjectionHistory([]);
    setLatestProjection(null);
    setActivity([]);
    setRiskEvents([]);
    setSessionSummary(null);
  };

  const applyTelemetry = (telemetry: any) => {
    setMarketData(telemetry.market_data ?? { prices: {}, changes: {} });
    setNews(telemetry.news ?? []);
    setActivity(telemetry.activity ?? []);
    setAllocations(telemetry.allocations ?? []);
    setProjectionHistory(telemetry.projection_history ?? []);
    setLatestProjection(telemetry.latest_projection ?? null);
    if (telemetry.portfolio) {
      setPortfolio(telemetry.portfolio);
    }
  };

  useEffect(() => {
    const loadBootstrap = async () => {
      try {
        const [scenarioRes, stateRes, tradeRes, boardRes, benchmarkRes, telemetryRes] = await Promise.all([
          fetch(`${API_BASE}/scenarios`),
          fetch(`${API_BASE}/state`),
          fetch(`${API_BASE}/trades`),
          fetch(`${API_BASE}/agents/leaderboard`),
          fetch(`${API_BASE}/benchmarks`),
          fetch(`${API_BASE}/telemetry`),
        ]);

        if (scenarioRes.ok) {
          setScenarios(await scenarioRes.json());
        }
        let state: ControlState = defaultControlState;
        if (stateRes.ok) {
          state = await stateRes.json();
          setControlState(state);
          setSessionActive(state.session_active);
        }
        if (tradeRes.ok && state.session_active) {
          setTrades((await tradeRes.json()).slice(0, 50));
        } else {
          setTrades([]);
        }
        if (boardRes.ok) {
          setLeaderboard(await boardRes.json());
        }
        if (benchmarkRes.ok) {
          const nextBenchmarkState: BenchmarkState = await benchmarkRes.json();
          benchmarkRef.current = nextBenchmarkState;
          setBenchmarkState(nextBenchmarkState);
        }
        if (telemetryRes.ok && state.session_active) {
          applyTelemetry(await telemetryRes.json());
        } else {
          clearLiveState();
        }
      } catch (error) {
        console.error("Bootstrap fetch failed", error);
      }
    };

    loadBootstrap();
  }, []);

  useEffect(() => {
    let cancelled = false;

    const refresh = async () => {
      try {
        const [stateRes, telemetryRes] = await Promise.all([
          fetch(`${API_BASE}/state`),
          fetch(`${API_BASE}/telemetry`),
        ]);

        if (!stateRes.ok || cancelled) {
          return;
        }

        const nextState: ControlState = await stateRes.json();
        if (cancelled) {
          return;
        }

        setControlState(nextState);
        setSessionActive(nextState.session_active);

        if (nextState.session_active && telemetryRes.ok) {
          applyTelemetry(await telemetryRes.json());
        } else if (!nextState.session_active) {
          clearLiveState();
        }
      } catch (error) {
        console.error("Polling refresh failed", error);
      }
    };

    refresh();
    const timer = window.setInterval(refresh, 2500);

    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
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
              setNews(msg.data.slice(0, 12));
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
            case "allocation_update":
              setAllocations(msg.data);
              break;
            case "projection_update":
              setLatestProjection(msg.data);
              setProjectionHistory((prev) => [...prev, msg.data].slice(-90));
              break;
            case "activity_event":
              setActivity((prev) => [msg.data, ...prev].slice(0, 80));
              break;
            case "risk_event":
              setRiskEvents((prev) => [msg.data, ...prev].slice(0, 12));
              break;
            case "control_state":
              setControlState(msg.data);
              setSessionActive(msg.data.session_active);
              break;
            case "scenario_update":
              setControlState((prev) => ({ ...prev, active_scenario: msg.data.active_scenario }));
              break;
            case "session_summary":
            case "session_end":
              setSessionActive(false);
              clearLiveState();
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
    setAllocations([]);
    setProjectionHistory([]);
    setLatestProjection(null);
    setActivity([]);
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
    allocations,
    projectionHistory,
    latestProjection,
    activity,
    riskEvents,
    controlState,
    scenarios,
    sessionSummary,
    startSession,
    applyScenario,
    setOverride,
    setAgentPaused,
  };
}
