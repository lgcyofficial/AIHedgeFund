"use client";

import { useDeferredValue, useMemo, useState } from "react";

import { useWebSocket } from "../hooks/useWebSocket";
import { ActivityEvent, AgentAllocation, MarketState, NewsItem, ProjectionPoint } from "../types";

const SESSION_DURATION_SECONDS = 60;
const PANEL =
  "rounded-[22px] border border-white/10 bg-[linear-gradient(180deg,rgba(14,18,24,0.98),rgba(7,10,15,0.98))] shadow-[0_22px_70px_rgba(0,0,0,0.38)] backdrop-blur";

function getSocketUrl() {
  if (typeof window === "undefined") {
    return "ws://127.0.0.1:8000/ws/stream";
  }
  const configured = process.env.NEXT_PUBLIC_WS_URL;
  if (configured) {
    return configured;
  }
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.hostname}:8000/ws/stream`;
}

function formatCurrency(value: number) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(value || 0);
}

function formatCompactCurrency(value: number) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    notation: "compact",
    maximumFractionDigits: 2,
  }).format(value || 0);
}

function formatSignedCurrency(value: number) {
  return `${value >= 0 ? "+" : "-"}${formatCurrency(Math.abs(value))}`;
}

function formatPercent(value: number) {
  return `${value >= 0 ? "+" : ""}${(value * 100).toFixed(2)}%`;
}

function formatShortTime(value: string) {
  return value?.slice(0, 5) || "--:--";
}

function normalizeCapitalInput(value: string) {
  const sanitized = value.replace(/[^\d.]/g, "");
  const [integerPartRaw, decimalPart] = sanitized.split(".", 2);
  const integerPart = integerPartRaw.replace(/^0+(?=\d)/, "");
  if (sanitized.includes(".")) {
    return `${integerPart || "0"}.${decimalPart ?? ""}`;
  }
  return integerPart;
}

function statusClasses(status: AgentAllocation["status"]) {
  if (status === "ACTIVE") {
    return "bg-emerald-500/[0.12] text-emerald-200 ring-1 ring-emerald-400/20";
  }
  if (status === "COOLDOWN") {
    return "bg-amber-500/[0.12] text-amber-100 ring-1 ring-amber-300/20";
  }
  return "bg-rose-500/[0.12] text-rose-200 ring-1 ring-rose-300/20";
}

function sentimentClasses(sentiment: NewsItem["sentiment"]) {
  if (sentiment === "positive") {
    return "text-emerald-200";
  }
  if (sentiment === "negative") {
    return "text-rose-200";
  }
  return "text-slate-300";
}

function agentBadgeClasses(agent?: string | null) {
  const key = (agent || "system").toLowerCase();
  if (key.includes("momentum")) {
    return "bg-cyan-500/[0.14] text-cyan-100 ring-1 ring-cyan-300/20";
  }
  if (key.includes("news")) {
    return "bg-orange-500/[0.14] text-orange-100 ring-1 ring-orange-300/20";
  }
  if (key.includes("macro")) {
    return "bg-lime-500/[0.14] text-lime-100 ring-1 ring-lime-300/20";
  }
  if (key.includes("volatility")) {
    return "bg-fuchsia-500/[0.14] text-fuchsia-100 ring-1 ring-fuchsia-300/20";
  }
  return "bg-white/[0.08] text-slate-200 ring-1 ring-white/10";
}

function chartTone(value: number) {
  return value >= 0 ? "text-emerald-200" : "text-rose-200";
}

function PerformanceChart({ history }: { history: ProjectionPoint[] }) {
  if (!history.length) {
    return <div className="flex h-full items-center justify-center text-sm text-slate-400">Waiting for live trade data...</div>;
  }

  const width = 720;
  const height = 260;
  const padding = 26;
  const values = history.flatMap((point) => [point.actual_pnl, point.projected_pnl, 0]);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const getX = (index: number) => padding + (index / Math.max(history.length - 1, 1)) * (width - padding * 2);
  const getY = (value: number) => height - padding - ((value - min) / range) * (height - padding * 2);
  const actualPath = history.map((point, index) => `${getX(index)},${getY(point.actual_pnl)}`).join(" ");
  const projectedPath = history.map((point, index) => `${getX(index)},${getY(point.projected_pnl)}`).join(" ");
  const latest = history[history.length - 1];

  return (
    <div className="relative h-full w-full">
      <div className="pointer-events-none absolute left-3 top-2 z-10 flex gap-3 rounded-full border border-white/10 bg-black/35 px-3 py-1.5 text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-200 backdrop-blur">
        <span className="inline-flex items-center gap-2">
          <span className="h-[3px] w-6 rounded-full bg-[#fb923c]" />
          P&amp;L
        </span>
        <span className="inline-flex items-center gap-2">
          <span className="h-[3px] w-6 rounded-full border-t-[3px] border-dashed border-[#2dd4bf]" />
          Projected P&amp;L
        </span>
      </div>
      <svg viewBox={`0 0 ${width} ${height}`} className="h-full w-full">
        {[0, 0.25, 0.5, 0.75, 1].map((ratio) => {
          const y = padding + ratio * (height - padding * 2);
          return <line key={ratio} x1={padding} x2={width - padding} y1={y} y2={y} stroke="rgba(255,255,255,0.08)" strokeDasharray="4 10" />;
        })}
        <line x1={padding} x2={width - padding} y1={getY(0)} y2={getY(0)} stroke="rgba(255,255,255,0.18)" />
        <polyline fill="none" stroke="#fb923c" strokeWidth="3.2" points={actualPath} />
        <polyline fill="none" stroke="#2dd4bf" strokeWidth="2.9" strokeDasharray="8 8" points={projectedPath} />
        <circle cx={getX(history.length - 1)} cy={getY(latest.actual_pnl)} r="4.5" fill="#fb923c" />
        <circle cx={getX(history.length - 1)} cy={getY(latest.projected_pnl)} r="4.5" fill="#2dd4bf" />
      </svg>
    </div>
  );
}

function PnlPanel({
  projectionHistory,
  latestProjection,
  portfolioValue,
  totalReturn,
}: {
  projectionHistory: ProjectionPoint[];
  latestProjection: ProjectionPoint | null;
  portfolioValue: number;
  totalReturn: number;
}) {
  const actualPnl = latestProjection?.actual_pnl ?? 0;
  const projectedPnl = latestProjection?.projected_pnl ?? 0;

  return (
    <section className={`${PANEL} flex min-h-0 flex-col p-4`}>
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-[10px] uppercase tracking-[0.34em] text-orange-300/80">Trade P&L</div>
          <h2 className="mt-2 text-2xl font-semibold text-slate-50">Real-time profit and loss</h2>
        </div>
        <div className="flex gap-2 text-[10px] uppercase tracking-[0.22em]">
          <span className="rounded-full bg-orange-500/[0.12] px-3 py-1 text-orange-100 ring-1 ring-orange-300/20">Actual</span>
          <span className="rounded-full bg-teal-500/[0.12] px-3 py-1 text-teal-100 ring-1 ring-teal-300/20">Projected</span>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
        <div className="rounded-[18px] border border-white/10 bg-black/[0.18] p-3">
          <div className="text-[10px] uppercase tracking-[0.22em] text-slate-500">NAV</div>
          <div className="mt-2 text-xl font-semibold text-slate-50">{formatCompactCurrency(portfolioValue)}</div>
        </div>
        <div className="rounded-[18px] border border-white/10 bg-black/[0.18] p-3">
          <div className="text-[10px] uppercase tracking-[0.22em] text-slate-500">Return</div>
          <div className={`mt-2 text-xl font-semibold ${chartTone(totalReturn)}`}>{formatPercent(totalReturn)}</div>
        </div>
        <div className="rounded-[18px] border border-white/10 bg-black/[0.18] p-3">
          <div className="text-[10px] uppercase tracking-[0.22em] text-slate-500">Live P&L</div>
          <div className={`mt-2 text-xl font-semibold ${chartTone(actualPnl)}`}>{formatSignedCurrency(actualPnl)}</div>
        </div>
        <div className="rounded-[18px] border border-white/10 bg-black/[0.18] p-3">
          <div className="text-[10px] uppercase tracking-[0.22em] text-slate-500">Forward P&L</div>
          <div className={`mt-2 text-xl font-semibold ${chartTone(projectedPnl)}`}>{formatSignedCurrency(projectedPnl)}</div>
        </div>
      </div>

      <div className="mt-4 min-h-[280px] flex-1 overflow-hidden rounded-[20px] border border-white/10 bg-[radial-gradient(circle_at_top,rgba(255,255,255,0.06),transparent_46%),linear-gradient(180deg,rgba(7,10,15,0.92),rgba(5,8,11,0.98))] p-3">
        <PerformanceChart history={projectionHistory} />
      </div>
    </section>
  );
}

function AllocationTable({
  allocations,
  pausedAgents,
  onToggleAgent,
}: {
  allocations: AgentAllocation[];
  pausedAgents: string[];
  onToggleAgent: (agent: string, paused: boolean) => Promise<void>;
}) {
  return (
    <section className={`${PANEL} flex min-h-0 flex-col p-4`}>
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <div className="text-[10px] uppercase tracking-[0.34em] text-orange-300/80">Treasury Split</div>
          <h2 className="mt-2 text-xl font-semibold text-slate-50">Capital allocated by agent</h2>
        </div>
      </div>

      <div className="min-h-0 overflow-auto rounded-[18px] border border-white/10 bg-black/[0.18]">
        <table className="min-w-full text-left text-sm">
          <thead className="sticky top-0 bg-[rgba(8,11,16,0.96)] text-[10px] uppercase tracking-[0.2em] text-slate-500">
            <tr>
              <th className="px-4 py-3">Agent</th>
              <th className="px-4 py-3">Capital</th>
              <th className="px-4 py-3">Cash</th>
              <th className="px-4 py-3">Deployed</th>
              <th className="px-4 py-3">Share</th>
              <th className="px-4 py-3">P&L</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3 text-right">Control</th>
            </tr>
          </thead>
          <tbody>
            {allocations.length === 0 ? (
              <tr>
                <td colSpan={8} className="px-4 py-6 text-center text-sm text-slate-400">
                  Agent allocations will populate when the trading session starts.
                </td>
              </tr>
            ) : (
              allocations.map((agent) => {
                const pnl = agent.realized_pnl + agent.unrealized_pnl;
                const paused = pausedAgents.includes(agent.agent);
                return (
                  <tr key={agent.agent} className="border-t border-white/6">
                    <td className="px-4 py-3">
                      <div className="font-medium text-slate-50">{agent.agent}</div>
                      <div className="mt-1 text-[11px] uppercase tracking-[0.16em] text-slate-500">{agent.last_decision}</div>
                    </td>
                    <td className="px-4 py-3 text-slate-200">{formatCompactCurrency(agent.capital)}</td>
                    <td className="px-4 py-3 text-slate-300">{formatCompactCurrency(agent.cash)}</td>
                    <td className="px-4 py-3 text-slate-300">{formatCompactCurrency(agent.deployed)}</td>
                    <td className="px-4 py-3 text-slate-300">{(agent.share_pct * 100).toFixed(1)}%</td>
                    <td className={`px-4 py-3 font-medium ${pnl >= 0 ? "text-emerald-200" : "text-rose-200"}`}>{formatSignedCurrency(pnl)}</td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex rounded-full px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.18em] ${statusClasses(agent.status)}`}>
                        {agent.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        onClick={() => void onToggleAgent(agent.agent, !paused)}
                        className="rounded-full border border-white/10 bg-white/[0.04] px-3 py-1.5 text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-200 transition hover:bg-white/[0.08]"
                      >
                        {paused ? "Resume" : "Pause"}
                      </button>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function ConversationPanel({ activity, coordination }: { activity: ActivityEvent[]; coordination: string }) {
  return (
    <section className={`${PANEL} flex min-h-0 flex-col p-4`}>
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <div className="text-[10px] uppercase tracking-[0.34em] text-orange-300/80">Agent Dialogue</div>
          <h2 className="mt-2 text-xl font-semibold text-slate-50">Agents discussing trades live</h2>
        </div>
        <div className="rounded-full bg-white/[0.06] px-3 py-1 text-[10px] uppercase tracking-[0.18em] text-slate-300">Runtime feed</div>
      </div>

      <div className="mb-4 rounded-[18px] border border-cyan-400/20 bg-cyan-400/[0.06] px-4 py-3 text-sm leading-6 text-slate-200">
        {coordination || "The committee is standing by for the next market update."}
      </div>

      <div className="min-h-0 space-y-3 overflow-y-auto pr-1">
        {activity.length === 0 ? (
          <div className="rounded-[18px] border border-dashed border-white/10 bg-black/[0.18] p-4 text-sm text-slate-400">
            Committee votes, pushback, treasury reallocations, and executions will stream here during the run.
          </div>
        ) : (
          activity.map((event) => (
            <article key={event.id} className="rounded-[20px] border border-white/10 bg-black/[0.18] p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className={`rounded-full px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.2em] ${agentBadgeClasses(event.agent)}`}>
                    {event.agent || "System"}
                  </span>
                  {event.target_agent ? (
                    <span className="rounded-full bg-white/[0.06] px-3 py-1 text-[10px] uppercase tracking-[0.2em] text-slate-300">
                      to {event.target_agent}
                    </span>
                  ) : null}
                  <span className="rounded-full bg-white/[0.06] px-3 py-1 text-[10px] uppercase tracking-[0.2em] text-slate-400">
                    {event.kind}
                  </span>
                </div>
                <div className="text-[11px] uppercase tracking-[0.18em] text-slate-500">{event.time}</div>
              </div>

              <div className="mt-3 text-sm font-semibold uppercase tracking-[0.14em] text-slate-400">{event.headline}</div>
              <p className="mt-2 text-[15px] leading-7 text-slate-100">{event.message}</p>

              <div className="mt-4 flex flex-wrap gap-2 text-[10px] uppercase tracking-[0.18em] text-slate-400">
                {event.asset ? <span className="rounded-full bg-white/[0.06] px-3 py-1">{event.asset}</span> : null}
                {typeof event.amount === "number" ? <span className="rounded-full bg-white/[0.06] px-3 py-1">{formatCompactCurrency(event.amount)}</span> : null}
                {typeof event.confidence === "number" ? (
                  <span className="rounded-full bg-white/[0.06] px-3 py-1">{(event.confidence * 100).toFixed(0)}% confidence</span>
                ) : null}
              </div>
            </article>
          ))
        )}
      </div>
    </section>
  );
}

function NewsPanel({ news, marketData }: { news: NewsItem[]; marketData: MarketState }) {
  const priceRows = Object.entries(marketData.prices).slice(0, 5);

  return (
    <section className={`${PANEL} flex min-h-0 flex-col p-4`}>
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <div className="text-[10px] uppercase tracking-[0.34em] text-orange-300/80">Live News Desk</div>
          <h2 className="mt-2 text-xl font-semibold text-slate-50">Market headlines</h2>
        </div>
        <div className="rounded-full bg-teal-400/[0.1] px-3 py-1 text-[10px] uppercase tracking-[0.18em] text-teal-100">Live tape</div>
      </div>

      <div className="mb-4 grid grid-cols-2 gap-2 xl:grid-cols-5">
        {priceRows.map(([asset, price]) => {
          const change = marketData.changes[asset] ?? 0;
          return (
            <div key={asset} className="rounded-[16px] border border-white/10 bg-black/[0.18] px-3 py-2.5">
              <div className="text-[10px] uppercase tracking-[0.18em] text-slate-500">{asset}</div>
              <div className="mt-1 text-sm font-semibold text-slate-50">{formatCompactCurrency(price)}</div>
              <div className={`mt-1 text-xs ${change >= 0 ? "text-emerald-200" : "text-rose-200"}`}>{formatPercent(change)}</div>
            </div>
          );
        })}
      </div>

      <div className="min-h-0 overflow-auto rounded-[18px] border border-white/10 bg-black/[0.18]">
        <table className="min-w-full text-left text-sm">
          <thead className="sticky top-0 bg-[rgba(8,11,16,0.96)] text-[10px] uppercase tracking-[0.2em] text-slate-500">
            <tr>
              <th className="px-4 py-3">Time</th>
              <th className="px-4 py-3">Source</th>
              <th className="px-4 py-3">Headline</th>
              <th className="px-4 py-3">Assets</th>
              <th className="px-4 py-3">Sentiment</th>
              <th className="px-4 py-3">Impact</th>
            </tr>
          </thead>
          <tbody>
            {news.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-4 py-6 text-center text-sm text-slate-400">
                  Live headlines will appear here when the backend starts streaming them.
                </td>
              </tr>
            ) : (
              news.map((item, index) => (
                <tr key={`${item.title}-${index}`} className="border-t border-white/6 align-top">
                  <td className="px-4 py-3 whitespace-nowrap text-slate-400">{formatShortTime(item.time)}</td>
                  <td className="px-4 py-3 text-slate-300">{item.source}</td>
                  <td className="px-4 py-3">
                    <div className="max-w-[28rem] leading-6 text-slate-100">{item.title}</div>
                    <div className="mt-2 text-[10px] uppercase tracking-[0.18em] text-slate-500">{item.category}</div>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-2">
                      {(item.assets?.length ? item.assets : ["MARKET"]).map((asset) => (
                        <span key={`${item.title}-${asset}`} className="rounded-full bg-white/[0.06] px-3 py-1 text-[10px] uppercase tracking-[0.18em] text-slate-200">
                          {asset}
                        </span>
                      ))}
                    </div>
                  </td>
                  <td className={`px-4 py-3 font-medium ${sentimentClasses(item.sentiment)}`}>{item.sentiment}</td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-3">
                      <div className="h-2 w-24 overflow-hidden rounded-full bg-white/[0.08]">
                        <div
                          className="h-full rounded-full bg-[linear-gradient(90deg,#38bdf8,#2dd4bf,#fb923c)]"
                          style={{ width: `${(item.impact_score ?? 0) * 100}%` }}
                        />
                      </div>
                      <span className="text-slate-300">{Math.round((item.impact_score ?? 0) * 100)}</span>
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export default function Dashboard() {
  const socketUrl = useMemo(() => getSocketUrl(), []);
  const {
    isConnected,
    portfolio,
    marketData,
    sessionActive,
    coordination,
    allocations,
    projectionHistory,
    latestProjection,
    activity,
    news,
    controlState,
    scenarios,
    startSession,
    applyScenario,
    setOverride,
    setAgentPaused,
  } = useWebSocket(socketUrl);

  const [capitalInput, setCapitalInput] = useState("10000");
  const [risk, setRisk] = useState("medium");
  const [selectedScenario, setSelectedScenario] = useState("");
  const [error, setError] = useState("");

  const deferredActivity = useDeferredValue(activity);
  const deferredNews = useDeferredValue(news);
  const activeScenario = selectedScenario || scenarios[0]?.id || "";
  const capital = Number(capitalInput) || 0;
  const navValue = portfolio?.total_value ?? capital;
  const totalReturn = portfolio?.total_return_pct ?? 0;

  const sessionLabel = useMemo(() => {
    if (!isConnected) {
      return "Backend offline";
    }
    return sessionActive ? "Session running" : "Ready";
  }, [isConnected, sessionActive]);

  const conversationFeed = useMemo(
    () => deferredActivity.filter((item) => item.kind !== "news").slice(0, 40),
    [deferredActivity],
  );

  const handleStart = async () => {
    try {
      setError("");
      await startSession(capital, risk, SESSION_DURATION_SECONDS, activeScenario);
    } catch (err) {
      setError("Could not start the session.");
      console.error(err);
    }
  };

  const handleScenarioApply = async () => {
    if (!activeScenario) {
      return;
    }

    try {
      setError("");
      await applyScenario(activeScenario);
      setSelectedScenario(activeScenario);
    } catch (err) {
      setError("Scenario injection failed.");
      console.error(err);
    }
  };

  return (
    <div
      className="min-h-[100dvh] bg-[#05070b] px-4 py-4 text-slate-100 sm:px-5"
      style={{
        backgroundImage:
          "radial-gradient(circle at 10% 0%, rgba(251,146,60,0.14), transparent 28%), radial-gradient(circle at 100% 10%, rgba(45,212,191,0.1), transparent 24%), linear-gradient(180deg, #090d14 0%, #05070b 100%)",
      }}
    >
      <div className="mx-auto flex min-h-[calc(100dvh-2rem)] max-w-[1960px] flex-col gap-3">
        <header className={`${PANEL} grid gap-3 px-4 py-3 xl:grid-cols-[minmax(0,1fr),auto] xl:items-center`}>
          <div className="flex min-w-0 flex-wrap items-center gap-3 overflow-hidden">
            <div className={`h-2.5 w-2.5 rounded-full ${isConnected ? "bg-emerald-400" : "bg-rose-400"}`} />
            <div className="text-[11px] font-medium uppercase tracking-[0.34em] text-slate-500">AI Hedge Fund Terminal</div>
            <div className="hidden h-4 w-px bg-white/[0.08] xl:block" />
            <div className="flex flex-wrap items-center gap-3 text-xs text-slate-300">
              <span>{sessionLabel}</span>
              <span className="text-slate-600">NAV {formatCompactCurrency(navValue)}</span>
              <span className={totalReturn >= 0 ? "text-emerald-200" : "text-rose-200"}>{formatPercent(totalReturn)}</span>
              {error ? <span className="text-rose-200">{error}</span> : null}
            </div>
          </div>

          <div className="grid gap-2 sm:grid-cols-3 xl:grid-cols-[96px,86px,86px,160px,88px,92px,92px]">
            <label className="rounded-[14px] border border-white/10 bg-black/[0.18] px-3 py-2">
              <div className="text-[9px] uppercase tracking-[0.16em] text-slate-500">Capital</div>
              <input
                type="text"
                inputMode="decimal"
                value={capitalInput}
                onChange={(event) => setCapitalInput(normalizeCapitalInput(event.target.value))}
                className="mt-1 w-full bg-transparent text-[11px] font-semibold outline-none"
              />
            </label>
            <label className="rounded-[14px] border border-white/10 bg-black/[0.18] px-3 py-2">
              <div className="text-[9px] uppercase tracking-[0.16em] text-slate-500">Risk</div>
              <select value={risk} onChange={(event) => setRisk(event.target.value)} className="mt-1 w-full bg-transparent text-[11px] font-semibold outline-none">
                <option className="bg-slate-900" value="low">Low</option>
                <option className="bg-slate-900" value="medium">Medium</option>
                <option className="bg-slate-900" value="high">High</option>
              </select>
            </label>
            <div className="rounded-[14px] border border-white/10 bg-black/[0.18] px-3 py-2">
              <div className="text-[9px] uppercase tracking-[0.16em] text-slate-500">Run Time</div>
              <div className="mt-1 text-[11px] font-semibold text-slate-100">{SESSION_DURATION_SECONDS}s fixed</div>
            </div>
            <label className="rounded-[14px] border border-white/10 bg-black/[0.18] px-3 py-2 sm:col-span-2 lg:col-span-1">
              <div className="text-[9px] uppercase tracking-[0.16em] text-slate-500">Scenario</div>
              <select
                value={activeScenario}
                onChange={(event) => setSelectedScenario(event.target.value)}
                className="mt-1 w-full bg-transparent text-[11px] font-semibold outline-none"
              >
                {scenarios.map((scenario) => (
                  <option key={scenario.id} value={scenario.id} className="bg-slate-900">
                    {scenario.title}
                  </option>
                ))}
              </select>
            </label>
            <button
              onClick={() => void handleScenarioApply()}
              className="rounded-[14px] border border-white/10 bg-white/[0.05] px-3 py-2 text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-100 transition hover:bg-white/[0.08]"
            >
              Inject
            </button>
            <button
              onClick={() => void setOverride(!controlState.override_active)}
              className={`rounded-[14px] px-3 py-2 text-[10px] font-semibold uppercase tracking-[0.18em] transition ${
                controlState.override_active
                  ? "bg-rose-500/[0.16] text-rose-100 ring-1 ring-rose-300/20"
                  : "border border-white/10 bg-white/[0.05] text-slate-300 hover:bg-white/[0.08]"
              }`}
            >
              Override
            </button>
            <button
              onClick={() => void handleStart()}
              disabled={!isConnected || sessionActive}
              className="rounded-[14px] bg-[#f59e0b] px-3 py-2 text-[10px] font-semibold uppercase tracking-[0.18em] text-black transition hover:bg-[#f0a11d] disabled:cursor-not-allowed disabled:opacity-40"
            >
              {sessionActive ? "Running" : "Start"}
            </button>
          </div>
        </header>

        <main className="grid min-h-0 flex-1 gap-3 md:grid-cols-[minmax(680px,1.45fr),minmax(0,1fr)]">
          <div className="grid min-h-0 gap-3 lg:grid-rows-[1.05fr,0.95fr]">
            <PnlPanel
              projectionHistory={projectionHistory}
              latestProjection={latestProjection}
              portfolioValue={navValue}
              totalReturn={totalReturn}
            />
            <AllocationTable allocations={allocations} pausedAgents={controlState.paused_agents} onToggleAgent={setAgentPaused} />
          </div>
          <div className="grid min-h-0 gap-3 md:grid-cols-2">
            <ConversationPanel activity={conversationFeed} coordination={coordination} />
            <NewsPanel news={deferredNews} marketData={marketData as MarketState} />
          </div>
        </main>
      </div>
    </div>
  );
}
