"use client";

import { useMemo, useState } from "react";

import { useWebSocket } from "../hooks/useWebSocket";
import { AgentLeaderboardEntry, BacktestLab, BenchmarkState, FactorExposure, ThemeExposure, Trade } from "../types";

const SOCKET_URL = "ws://127.0.0.1:8000/ws/stream";
const PANEL =
  "rounded-[28px] border border-white/10 bg-[linear-gradient(180deg,rgba(18,24,38,0.9),rgba(7,10,18,0.94))] shadow-[0_24px_80px_rgba(0,0,0,0.45)] backdrop-blur";

function formatCurrency(value: number) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  }).format(value || 0);
}

function formatPercent(value: number) {
  return `${value >= 0 ? "+" : ""}${(value * 100).toFixed(2)}%`;
}

function buildChartSeries(
  history: { time: number; fund: number; benchmarks: Record<string, number> }[],
  benchmarkState: BenchmarkState,
) {
  if (!history.length) {
    return [];
  }

  const names = ["Fund", ...Object.keys(benchmarkState.values)];
  return names.map((name) => ({
    name,
    color:
      name === "Fund"
        ? "#FF6B3D"
        : name === "SPY"
          ? "#4DD6C0"
          : name === "QQQ"
            ? "#F4D35E"
            : "#89A6FB",
    points: history.map((point, index) => {
      const value = name === "Fund" ? point.fund : point.benchmarks[name] ?? point.fund;
      return { x: index, value };
    }),
  }));
}

function PerformanceChart({
  history,
  benchmarkState,
}: {
  history: { time: number; fund: number; benchmarks: Record<string, number> }[];
  benchmarkState: BenchmarkState;
}) {
  const series = buildChartSeries(history, benchmarkState);

  if (!series.length) {
    return <div className="flex h-full items-center justify-center text-sm text-white/40">Waiting for live data...</div>;
  }

  const width = 680;
  const height = 260;
  const padding = 26;
  const allValues = series.flatMap((line) => line.points.map((point) => point.value));
  const minValue = Math.min(...allValues);
  const maxValue = Math.max(...allValues);
  const range = maxValue - minValue || 1;

  const getX = (index: number, total: number) =>
    padding + (index / Math.max(total - 1, 1)) * (width - padding * 2);
  const getY = (value: number) => height - padding - ((value - minValue) / range) * (height - padding * 2);

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="h-full w-full">
      <defs>
        <filter id="chartGlow">
          <feGaussianBlur stdDeviation="2.5" result="coloredBlur" />
          <feMerge>
            <feMergeNode in="coloredBlur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>
      <rect x="0" y="0" width={width} height={height} rx="24" fill="transparent" />
      {[0.2, 0.4, 0.6, 0.8].map((ratio) => (
        <line
          key={ratio}
          x1={padding}
          x2={width - padding}
          y1={padding + ratio * (height - padding * 2)}
          y2={padding + ratio * (height - padding * 2)}
          stroke="rgba(255,255,255,0.08)"
          strokeDasharray="4 8"
        />
      ))}
      {series.map((line) => (
        <polyline
          key={line.name}
          fill="none"
          stroke={line.color}
          strokeWidth={line.name === "Fund" ? 3.5 : 2}
          filter="url(#chartGlow)"
          points={line.points.map((point, index) => `${getX(index, line.points.length)},${getY(point.value)}`).join(" ")}
        />
      ))}
    </svg>
  );
}

function LeaderboardCard({
  leaderboard,
  pausedAgents,
  onToggleAgent,
}: {
  leaderboard: AgentLeaderboardEntry[];
  pausedAgents: string[];
  onToggleAgent: (agent: string, paused: boolean) => Promise<void>;
}) {
  return (
    <div className={`${PANEL} p-5`}>
      <div className="mb-4 flex items-center justify-between">
        <div>
          <div className="text-xs uppercase tracking-[0.24em] text-white/40">Agent Leaderboard</div>
          <div className="text-lg font-semibold text-white">Capital earns merit</div>
        </div>
      </div>
      <div className="space-y-3">
        {leaderboard.map((agent, index) => {
          const score = agent.realized_pnl + agent.unrealized_pnl;
          const paused = pausedAgents.includes(agent.agent);
          return (
            <div key={agent.agent} className="rounded-2xl border border-white/8 bg-white/[0.03] p-4">
              <div className="mb-2 flex items-center justify-between gap-4">
                <div>
                  <div className="text-xs uppercase tracking-[0.22em] text-white/35">#{index + 1}</div>
                  <div className="text-sm font-semibold text-white">{agent.agent}</div>
                </div>
                <button
                  onClick={() => void onToggleAgent(agent.agent, !paused)}
                  className={`rounded-full px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.2em] ${
                    paused ? "bg-red-500/20 text-red-200" : "bg-white/8 text-white/70"
                  }`}
                >
                  {paused ? "Resume" : "Pause"}
                </button>
              </div>
              <div className="grid grid-cols-2 gap-2 text-sm">
                <div className="rounded-xl bg-black/20 p-2 text-white/65">PnL {formatCurrency(score)}</div>
                <div className="rounded-xl bg-black/20 p-2 text-white/65">Win rate {(agent.win_rate * 100).toFixed(0)}%</div>
                <div className="rounded-xl bg-black/20 p-2 text-white/65">Deployed {formatCurrency(agent.deployed)}</div>
                <div className="rounded-xl bg-black/20 p-2 text-white/65">Last {agent.last_decision}</div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function TradeCard({ trade }: { trade: Trade }) {
  return (
    <div className="rounded-2xl border border-white/8 bg-white/[0.03] p-4">
      <div className="mb-2 flex items-center justify-between gap-3">
        <div>
          <div className="text-xs uppercase tracking-[0.22em] text-white/35">{trade.agent}</div>
          <div className="text-lg font-semibold text-white">
            {trade.action} {trade.asset}
          </div>
        </div>
        <div
          className={`rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-[0.2em] ${
            trade.committee_approved ? "bg-emerald-400/15 text-emerald-200" : "bg-red-500/15 text-red-200"
          }`}
        >
          {trade.committee_approved ? "Approved" : "Rejected"}
        </div>
      </div>
      <div className="grid grid-cols-2 gap-2 text-sm text-white/65">
        <div className="rounded-xl bg-black/20 p-2">Size {formatCurrency(trade.amount)}</div>
        <div className="rounded-xl bg-black/20 p-2">Confidence {(trade.confidence * 100).toFixed(0)}%</div>
        <div className="rounded-xl bg-black/20 p-2">Catalyst {trade.catalyst || "Price action"}</div>
        <div className="rounded-xl bg-black/20 p-2">Expected move {trade.expected_move || "n/a"}</div>
      </div>
      <div className="mt-3 text-sm text-white/78">{trade.thesis || trade.reasoning}</div>
    </div>
  );
}

function ThemeExposureMap({ exposures }: { exposures: ThemeExposure[] }) {
  if (!exposures.length) {
    return <div className="rounded-2xl border border-dashed border-white/10 bg-black/20 p-4 text-sm text-white/45">Theme exposures appear once the fund takes risk.</div>;
  }

  return (
    <div className="space-y-3">
      {exposures.map((exposure, index) => (
        <div key={exposure.theme} className="rounded-2xl border border-white/8 bg-white/[0.03] p-4">
          <div className="mb-2 flex items-center justify-between gap-3">
            <div>
              <div className="text-sm font-semibold text-white">{exposure.theme}</div>
              <div className="text-xs uppercase tracking-[0.2em] text-white/35">Theme sleeve #{index + 1}</div>
            </div>
            <div className="text-right">
              <div className="text-sm font-semibold text-white">{formatPercent(exposure.weight)}</div>
              <div className="text-xs text-white/40">{formatCurrency(exposure.value)}</div>
            </div>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-white/8">
            <div
              className="h-full rounded-full bg-[linear-gradient(90deg,#4DD6C0,#FF6B3D)]"
              style={{ width: `${Math.min(exposure.weight * 100, 100)}%` }}
            />
          </div>
          <div className="mt-3 grid gap-2 sm:grid-cols-2">
            {Object.entries(exposure.assets).map(([asset, value]) => (
              <div key={`${exposure.theme}-${asset}`} className="rounded-xl bg-black/20 p-2 text-sm text-white/62">
                {asset} {formatCurrency(value)}
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function FactorExposureMap({ exposures }: { exposures: FactorExposure[] }) {
  if (!exposures.length) {
    return <div className="rounded-2xl border border-dashed border-white/10 bg-black/20 p-4 text-sm text-white/45">Factor exposures appear after positions are established.</div>;
  }

  return (
    <div className="grid gap-3">
      {exposures.map((exposure) => (
        <div key={exposure.factor} className="rounded-2xl border border-white/8 bg-white/[0.03] p-4">
          <div className="mb-2 flex items-center justify-between">
            <div className="text-sm font-semibold text-white">{exposure.factor}</div>
            <div className="text-sm text-white/60">{formatPercent(exposure.weight)}</div>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-white/8">
            <div
              className="h-full rounded-full bg-[linear-gradient(90deg,#89A6FB,#4DD6C0)]"
              style={{ width: `${Math.min(exposure.weight * 100, 100)}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

function BacktestLabCard({ lab }: { lab: BacktestLab | null }) {
  if (!lab) {
    return <div className="rounded-2xl border border-dashed border-white/10 bg-black/20 p-4 text-sm text-white/45">Backtest lab is loading.</div>;
  }

  return (
    <div className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-3">
        <div className="rounded-2xl bg-black/20 p-3 text-sm text-white/65">
          Beat rate <span className="font-semibold text-white">{formatPercent(lab.beat_rate)}</span>
        </div>
        <div className="rounded-2xl bg-black/20 p-3 text-sm text-white/65">
          Avg alpha <span className="font-semibold text-white">{formatPercent(lab.average_alpha_pct)}</span>
        </div>
        <div className="rounded-2xl bg-black/20 p-3 text-sm text-white/65">
          Best run <span className="font-semibold text-white">{lab.best_run?.scenario_title ?? "n/a"}</span>
        </div>
      </div>
      <div className="rounded-2xl border border-white/8 bg-white/[0.03] p-4 text-sm text-white/62">{lab.summary}</div>
      <div className="max-h-[320px] overflow-y-auto rounded-2xl border border-white/8 bg-white/[0.03]">
        <table className="w-full text-left text-sm">
          <thead className="sticky top-0 bg-[#111827] text-white/45">
            <tr>
              <th className="px-4 py-3 font-medium">Scenario</th>
              <th className="px-4 py-3 font-medium">Risk</th>
              <th className="px-4 py-3 font-medium">Return</th>
              <th className="px-4 py-3 font-medium">Alpha</th>
              <th className="px-4 py-3 font-medium">Drawdown</th>
            </tr>
          </thead>
          <tbody>
            {lab.runs.map((run, index) => (
              <tr key={`${run.scenario_id}-${run.risk}`} className={index % 2 === 0 ? "bg-black/10" : ""}>
                <td className="px-4 py-3 text-white/70">{run.scenario_title}</td>
                <td className="px-4 py-3 uppercase text-white/55">{run.risk}</td>
                <td className="px-4 py-3 text-white/70">{formatPercent(run.return_pct)}</td>
                <td className={run.alpha_pct >= 0 ? "px-4 py-3 text-emerald-200" : "px-4 py-3 text-red-200"}>
                  {formatPercent(run.alpha_pct)}
                </td>
                <td className="px-4 py-3 text-white/60">{formatPercent(-Math.abs(run.max_drawdown_pct))}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function Dashboard() {
  const {
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
  } = useWebSocket(SOCKET_URL);

  const [capital, setCapital] = useState(10000);
  const [risk, setRisk] = useState("medium");
  const [duration, setDuration] = useState(60);
  const [selectedScenario, setSelectedScenario] = useState("");
  const [error, setError] = useState("");
  const activeScenario = selectedScenario || scenarios[0]?.id || "";

  const totalBenchmarkCards = useMemo(() => {
    return Object.entries(benchmarkState.returns).map(([name, value]) => ({
      name,
      value,
      benchmarkValue: benchmarkState.values[name] ?? 0,
    }));
  }, [benchmarkState]);

  const navValue = portfolio?.total_value ?? capital;
  const totalReturn = portfolio?.total_return_pct ?? 0;
  const themeExposures = portfolio?.theme_exposures ?? [];
  const factorExposures = portfolio?.factor_exposures ?? [];

  const handleStart = async () => {
    try {
      setError("");
      await startSession(capital, risk, duration, activeScenario);
    } catch (err) {
      setError("Could not start a new session.");
      console.error(err);
    }
  };

  const handleScenarioApply = async (scenarioId: string) => {
    try {
      setError("");
      await applyScenario(scenarioId);
      setSelectedScenario(scenarioId);
    } catch (err) {
      setError("Scenario injection failed.");
      console.error(err);
    }
  };

  const benchmarkWinner = totalBenchmarkCards.reduce(
    (best, next) => (next.value > best.value ? next : best),
    { name: "Fund", value: totalReturn, benchmarkValue: navValue },
  );

  return (
    <div
      className="min-h-screen bg-[#071018] px-4 py-5 text-white sm:px-6 lg:px-8"
      style={{
        backgroundImage:
          "radial-gradient(circle at 20% 10%, rgba(255,107,61,0.18), transparent 28%), radial-gradient(circle at 80% 0%, rgba(77,214,192,0.12), transparent 24%), linear-gradient(180deg, #0b1220 0%, #071018 50%, #05070d 100%)",
      }}
    >
      <div className="mx-auto flex max-w-[1600px] flex-col gap-5">
        <div className={`${PANEL} overflow-hidden p-5 sm:p-6`}>
          <div className="flex flex-col gap-6 xl:flex-row xl:items-end xl:justify-between">
            <div className="space-y-4">
              <div className="inline-flex items-center gap-3 rounded-full border border-white/10 bg-white/[0.04] px-4 py-2">
                <span className={`h-2.5 w-2.5 rounded-full ${isConnected ? "bg-emerald-300" : "bg-red-400"}`} />
                <span className="text-xs uppercase tracking-[0.32em] text-white/55">
                  {isConnected ? "Live feed online" : "Backend offline"}
                </span>
              </div>
              <div>
                <div className="text-xs uppercase tracking-[0.32em] text-white/40">Autonomous Multi-Agent Fund</div>
                <h1 className="text-4xl font-semibold tracking-tight sm:text-5xl">TradeAgent Command Deck</h1>
              </div>
              <div className="max-w-3xl text-sm text-white/68 sm:text-base">{coordination || "Ready for scenario-driven autonomous trading."}</div>
            </div>

            <div className="grid gap-3 sm:grid-cols-2 xl:min-w-[540px] xl:grid-cols-4">
              <label className="rounded-2xl border border-white/10 bg-black/20 p-3 text-sm">
                <div className="mb-2 text-[11px] uppercase tracking-[0.24em] text-white/40">Capital</div>
                <input
                  type="number"
                  value={capital}
                  onChange={(e) => setCapital(Number(e.target.value))}
                  className="w-full bg-transparent text-lg font-semibold outline-none"
                />
              </label>
              <label className="rounded-2xl border border-white/10 bg-black/20 p-3 text-sm">
                <div className="mb-2 text-[11px] uppercase tracking-[0.24em] text-white/40">Risk</div>
                <select value={risk} onChange={(e) => setRisk(e.target.value)} className="w-full bg-transparent text-lg font-semibold outline-none">
                  <option className="bg-slate-900" value="low">
                    Low
                  </option>
                  <option className="bg-slate-900" value="medium">
                    Medium
                  </option>
                  <option className="bg-slate-900" value="high">
                    High
                  </option>
                </select>
              </label>
              <label className="rounded-2xl border border-white/10 bg-black/20 p-3 text-sm">
                <div className="mb-2 text-[11px] uppercase tracking-[0.24em] text-white/40">Duration</div>
                <input
                  type="number"
                  value={duration}
                  onChange={(e) => setDuration(Number(e.target.value))}
                  className="w-full bg-transparent text-lg font-semibold outline-none"
                />
              </label>
              <label className="rounded-2xl border border-white/10 bg-black/20 p-3 text-sm">
                <div className="mb-2 text-[11px] uppercase tracking-[0.24em] text-white/40">Scenario</div>
                <select
                  value={activeScenario}
                  onChange={(e) => setSelectedScenario(e.target.value)}
                  className="w-full bg-transparent text-sm font-semibold outline-none"
                >
                  {scenarios.map((scenario) => (
                    <option key={scenario.id} value={scenario.id} className="bg-slate-900">
                      {scenario.title}
                    </option>
                  ))}
                </select>
              </label>
            </div>
          </div>

          <div className="mt-6 flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
            <div className="grid gap-3 sm:grid-cols-3 xl:w-[560px]">
              <div className="rounded-2xl border border-white/8 bg-black/20 p-4">
                <div className="text-xs uppercase tracking-[0.22em] text-white/40">NAV</div>
                <div className="mt-2 text-3xl font-semibold">{formatCurrency(navValue)}</div>
              </div>
              <div className="rounded-2xl border border-white/8 bg-black/20 p-4">
                <div className="text-xs uppercase tracking-[0.22em] text-white/40">Fund Return</div>
                <div className={`mt-2 text-3xl font-semibold ${totalReturn >= 0 ? "text-emerald-200" : "text-red-200"}`}>
                  {formatPercent(totalReturn)}
                </div>
              </div>
              <div className="rounded-2xl border border-white/8 bg-black/20 p-4">
                <div className="text-xs uppercase tracking-[0.22em] text-white/40">Best Benchmark</div>
                <div className="mt-2 text-3xl font-semibold">{benchmarkWinner.name}</div>
              </div>
            </div>

            <div className="flex flex-col gap-3 sm:flex-row">
              <button
                onClick={() => void handleScenarioApply(activeScenario)}
                disabled={!activeScenario}
                className="rounded-full border border-[#4DD6C0]/40 bg-[#4DD6C0]/12 px-5 py-3 text-sm font-semibold uppercase tracking-[0.24em] text-[#d5fff8]"
              >
                Inject Scenario
              </button>
              <button
                onClick={() => void setOverride(!controlState.override_active)}
                className={`rounded-full px-5 py-3 text-sm font-semibold uppercase tracking-[0.24em] ${
                  controlState.override_active
                    ? "border border-red-300/40 bg-red-500/18 text-red-100"
                    : "border border-white/10 bg-white/[0.05] text-white/70"
                }`}
              >
                {controlState.override_active ? "Override On" : "PM Override"}
              </button>
              <button
                onClick={() => void handleStart()}
                disabled={!isConnected || sessionActive}
                className="rounded-full bg-[#FF6B3D] px-6 py-3 text-sm font-semibold uppercase tracking-[0.24em] text-black disabled:cursor-not-allowed disabled:opacity-50"
              >
                {sessionActive ? "Session Running" : "Start Session"}
              </button>
            </div>
          </div>

          {error ? <div className="mt-4 text-sm text-red-200">{error}</div> : null}
        </div>

        <div className="grid gap-5 xl:grid-cols-[1.1fr,1.4fr,1fr]">
          <div className="flex flex-col gap-5">
            <div className={`${PANEL} p-5`}>
              <div className="mb-4 flex items-center justify-between">
                <div>
                  <div className="text-xs uppercase tracking-[0.24em] text-white/40">Benchmark Race</div>
                  <div className="text-lg font-semibold">Fund vs passive</div>
                </div>
              </div>
              <div className="h-64 overflow-hidden rounded-[24px] border border-white/8 bg-black/20 p-2">
                <PerformanceChart history={benchmarkHistory} benchmarkState={benchmarkState} />
              </div>
              <div className="mt-4 grid gap-3 sm:grid-cols-3">
                <div className="rounded-2xl bg-black/20 p-3 text-sm text-white/65">Fund {formatPercent(totalReturn)}</div>
                {totalBenchmarkCards.map((card) => (
                  <div key={card.name} className="rounded-2xl bg-black/20 p-3 text-sm text-white/65">
                    {card.name} {formatPercent(card.value)}
                  </div>
                ))}
              </div>
            </div>

            <div className={`${PANEL} p-5`}>
              <div className="mb-4 flex items-center justify-between">
                <div>
                  <div className="text-xs uppercase tracking-[0.24em] text-white/40">Research Desk</div>
                  <div className="text-lg font-semibold">Regime and thesis memo</div>
                </div>
              </div>
              <div className="space-y-3">
                <div className="rounded-2xl border border-white/8 bg-white/[0.03] p-4">
                  <div className="text-xs uppercase tracking-[0.2em] text-white/35">Regime</div>
                  <div className="mt-2 text-2xl font-semibold text-white">{researchBrief.regime}</div>
                  <div className="mt-2 text-sm text-white/62">{researchBrief.summary}</div>
                </div>
                <div className="rounded-2xl bg-black/20 p-4 text-sm text-white/68">
                  Primary risk: <span className="text-white">{researchBrief.primary_risk}</span>
                </div>
                <div className="grid gap-3">
                  <div className="rounded-2xl bg-black/20 p-4">
                    <div className="mb-2 text-xs uppercase tracking-[0.2em] text-white/35">Opportunities</div>
                    <div className="space-y-2">
                      {researchBrief.opportunities.map((item, index) => (
                        <div key={`${item}-${index}`} className="text-sm text-white/65">{item}</div>
                      ))}
                    </div>
                  </div>
                  <div className="rounded-2xl bg-black/20 p-4">
                    <div className="mb-2 text-xs uppercase tracking-[0.2em] text-white/35">Watchlist</div>
                    <div className="flex flex-wrap gap-2">
                      {researchBrief.watchlist.map((asset) => (
                        <span key={asset} className="rounded-full bg-white/8 px-3 py-1 text-xs uppercase tracking-[0.2em] text-white/72">
                          {asset}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <div className={`${PANEL} p-5`}>
              <div className="mb-4 flex items-center justify-between">
                <div>
                  <div className="text-xs uppercase tracking-[0.24em] text-white/40">Theme Exposure Map</div>
                  <div className="text-lg font-semibold">Portfolio by macro sleeve</div>
                </div>
              </div>
              <ThemeExposureMap exposures={themeExposures} />
            </div>

            <div className={`${PANEL} p-5`}>
              <div className="mb-4 flex items-center justify-between">
                <div>
                  <div className="text-xs uppercase tracking-[0.24em] text-white/40">Factor Exposure Model</div>
                  <div className="text-lg font-semibold">Style and beta decomposition</div>
                </div>
              </div>
              <FactorExposureMap exposures={factorExposures} />
            </div>

            <LeaderboardCard
              leaderboard={leaderboard}
              pausedAgents={controlState.paused_agents}
              onToggleAgent={setAgentPaused}
            />
          </div>

          <div className="flex flex-col gap-5">
            <div className={`${PANEL} p-5`}>
              <div className="mb-4 flex items-center justify-between">
                <div>
                  <div className="text-xs uppercase tracking-[0.24em] text-white/40">Portfolio Construction</div>
                  <div className="text-lg font-semibold">Overlay and crowding control</div>
                </div>
              </div>
              <div className="space-y-3">
                <div className="grid gap-3 sm:grid-cols-3">
                  <div className="rounded-2xl bg-black/20 p-3 text-sm text-white/65">
                    Status <span className="font-semibold text-white">{constructionState.status}</span>
                  </div>
                  <div className="rounded-2xl bg-black/20 p-3 text-sm text-white/65">
                    Dominant <span className="font-semibold text-white">{constructionState.dominant_theme ?? "None"}</span>
                  </div>
                  <div className="rounded-2xl bg-black/20 p-3 text-sm text-white/65">
                    Cash buffer <span className="font-semibold text-white">{formatPercent(constructionState.cash_buffer_weight)}</span>
                  </div>
                </div>
                <div className="rounded-2xl border border-white/8 bg-white/[0.03] p-4">
                  <div className="mb-2 text-xs uppercase tracking-[0.2em] text-white/35">Concentration score</div>
                  <div className="text-3xl font-semibold text-white">{constructionState.concentration_score.toFixed(2)}</div>
                  <div className="mt-2 text-sm text-white/55">Lower is more diversified. The overlay trims the book when a theme crowds out the rest of the fund.</div>
                </div>
                <div className="space-y-2">
                  {constructionState.actions.length === 0 ? (
                    <div className="rounded-2xl border border-dashed border-white/10 bg-black/20 p-4 text-sm text-white/45">
                      No construction actions yet. The overlay will log trims and blocked crowding here.
                    </div>
                  ) : (
                    constructionState.actions.map((action, index) => (
                      <div key={`${action.type}-${action.asset}-${index}`} className="rounded-2xl bg-black/20 p-4 text-sm text-white/68">
                        {action.message}
                        {action.amount > 0 ? ` (${formatCurrency(action.amount)})` : ""}
                      </div>
                    ))
                  )}
                </div>
                <div className="space-y-2">
                  {constructionState.notes.map((note, index) => (
                    <div key={`${note}-${index}`} className="rounded-xl bg-white/[0.03] p-3 text-sm text-white/55">
                      {note}
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <div className={`${PANEL} p-5`}>
              <div className="mb-4 flex items-center justify-between">
                <div>
                  <div className="text-xs uppercase tracking-[0.24em] text-white/40">Investment Committee</div>
                  <div className="text-lg font-semibold">Large-trade voting board</div>
                </div>
              </div>
              <div className="space-y-3">
                {committeeVotes.length === 0 ? (
                  <div className="rounded-2xl border border-dashed border-white/10 bg-black/20 p-5 text-sm text-white/45">
                    Large proposals will appear here with each agent vote and consensus score.
                  </div>
                ) : (
                  committeeVotes.map((vote, index) => (
                    <div key={`${vote.proposal_agent}-${index}`} className="rounded-2xl border border-white/8 bg-white/[0.03] p-4">
                      <div className="mb-3 flex items-center justify-between gap-3">
                        <div>
                          <div className="text-xs uppercase tracking-[0.22em] text-white/35">{vote.proposal_agent} proposal</div>
                          <div className="text-lg font-semibold text-white">
                            {vote.proposal.action} {vote.proposal.asset} {formatCurrency(vote.proposal.amount)}
                          </div>
                        </div>
                        <div
                          className={`rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-[0.2em] ${
                            vote.approved ? "bg-emerald-400/15 text-emerald-100" : "bg-red-500/15 text-red-100"
                          }`}
                        >
                          {vote.approved ? "Approved" : "Rejected"}
                        </div>
                      </div>
                      <div className="mb-3 text-sm text-white/60">Consensus {(vote.consensus * 100).toFixed(0)}%</div>
                      <div className="grid gap-2 sm:grid-cols-3">
                        {vote.votes.map((record) => (
                          <div key={`${vote.proposal_agent}-${record.agent}`} className="rounded-xl bg-black/20 p-3">
                            <div className="flex items-center justify-between">
                              <div className="text-sm font-semibold text-white">{record.agent}</div>
                              <div className={record.vote === "YES" ? "text-emerald-200" : "text-red-200"}>{record.vote}</div>
                            </div>
                            <div className="mt-2 text-xs leading-5 text-white/55">{record.reasoning}</div>
                          </div>
                        ))}
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>

            <div className={`${PANEL} p-5`}>
              <div className="mb-4 flex items-center justify-between">
                <div>
                  <div className="text-xs uppercase tracking-[0.24em] text-white/40">Reasoning Stream</div>
                  <div className="text-lg font-semibold">Why the agents are acting</div>
                </div>
              </div>
              <div className="max-h-[460px] space-y-3 overflow-y-auto pr-1">
                {reasonings.map((entry, index) => (
                  <div key={`${entry.agent}-${index}`} className="rounded-2xl border border-white/8 bg-white/[0.03] p-4">
                    <div className="mb-2 flex items-center justify-between gap-3">
                      <div className="text-sm font-semibold text-white">{entry.agent}</div>
                      <div className="rounded-full bg-black/20 px-3 py-1 text-xs uppercase tracking-[0.2em] text-white/55">
                        {entry.decision.action}
                      </div>
                    </div>
                    <div className="text-sm text-white/72">{entry.reasoning}</div>
                    <div className="mt-3 grid gap-2 sm:grid-cols-3">
                      <div className="rounded-xl bg-black/20 p-2 text-sm text-white/62">Asset {entry.decision.asset}</div>
                      <div className="rounded-xl bg-black/20 p-2 text-sm text-white/62">
                        Size {formatCurrency(entry.decision.amount)}
                      </div>
                      <div className="rounded-xl bg-black/20 p-2 text-sm text-white/62">
                        Conviction {(entry.decision.confidence * 100).toFixed(0)}%
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="flex flex-col gap-5">
            <div className={`${PANEL} p-5`}>
              <div className="mb-4 flex items-center justify-between">
                <div>
                  <div className="text-xs uppercase tracking-[0.24em] text-white/40">Scenario Deck</div>
                  <div className="text-lg font-semibold">Demo triggers</div>
                </div>
              </div>
              <div className="space-y-3">
                {scenarios.map((scenario) => (
                  <button
                    key={scenario.id}
                    onClick={() => void handleScenarioApply(scenario.id)}
                    className={`w-full rounded-2xl border p-4 text-left transition ${
                      selectedScenario === scenario.id
                        ? "border-[#FF6B3D]/50 bg-[#FF6B3D]/12"
                        : "border-white/8 bg-white/[0.03]"
                    }`}
                  >
                    <div className="text-sm font-semibold text-white">{scenario.title}</div>
                    <div className="mt-1 text-sm text-white/58">{scenario.description}</div>
                  </button>
                ))}
              </div>
            </div>

            <div className={`${PANEL} p-5`}>
              <div className="mb-4 flex items-center justify-between">
                <div>
                  <div className="text-xs uppercase tracking-[0.24em] text-white/40">Risk Radar</div>
                  <div className="text-lg font-semibold">Guardrails in motion</div>
                </div>
              </div>
              <div className="space-y-3">
                {riskEvents.length === 0 ? (
                  <div className="rounded-2xl border border-dashed border-white/10 bg-black/20 p-4 text-sm text-white/45">
                    No risk alerts yet. The engine will surface stop-losses, vetoes, and kill-switch events here.
                  </div>
                ) : (
                  riskEvents.map((event, index) => (
                    <div key={`${event.time}-${index}`} className="rounded-2xl border border-white/8 bg-white/[0.03] p-4">
                      <div className="flex items-center justify-between gap-3">
                        <div className="text-sm font-semibold text-white">{event.time || "now"}</div>
                        <div
                          className={`rounded-full px-3 py-1 text-xs uppercase tracking-[0.2em] ${
                            event.severity === "high" ? "bg-red-500/15 text-red-100" : "bg-amber-500/15 text-amber-100"
                          }`}
                        >
                          {event.severity}
                        </div>
                      </div>
                      <div className="mt-2 text-sm text-white/62">{event.message}</div>
                    </div>
                  ))
                )}
              </div>
            </div>

            <div className={`${PANEL} p-5`}>
              <div className="mb-4 flex items-center justify-between">
                <div>
                  <div className="text-xs uppercase tracking-[0.24em] text-white/40">Market + News</div>
                  <div className="text-lg font-semibold">Live narrative tape</div>
                </div>
              </div>
              <div className="grid gap-4 lg:grid-cols-1">
                <div className="space-y-2">
                  {Object.entries(marketData.prices).map(([asset, price]) => {
                    const change = marketData.changes[asset] ?? 0;
                    return (
                      <div key={asset} className="flex items-center justify-between rounded-2xl bg-black/20 p-3">
                        <div>
                          <div className="text-sm font-semibold text-white">{asset}</div>
                          <div className="text-xs uppercase tracking-[0.2em] text-white/35">Live tape</div>
                        </div>
                        <div className="text-right">
                          <div className="text-sm font-semibold text-white">{formatCurrency(price)}</div>
                          <div className={change >= 0 ? "text-emerald-200" : "text-red-200"}>{formatPercent(change)}</div>
                        </div>
                      </div>
                    );
                  })}
                </div>
                <div className="space-y-2">
                  {news.map((item, index) => (
                    <div key={`${item.title}-${index}`} className="rounded-2xl bg-black/20 p-3">
                      <div className="text-xs uppercase tracking-[0.2em] text-white/35">{item.time || "headline"}</div>
                      <div className="mt-1 text-sm text-white/68">{item.title}</div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>

        <div className="grid gap-5 xl:grid-cols-[1.2fr,1fr]">
          <div className={`${PANEL} p-5`}>
            <div className="mb-5">
              <div className="text-xs uppercase tracking-[0.24em] text-white/40">Backtest Lab</div>
              <div className="text-lg font-semibold">Scenario and risk-mandate matrix</div>
            </div>
            <BacktestLabCard lab={backtestLab} />
          </div>

          <div className={`${PANEL} p-5`}>
            <div className="mb-4 flex items-center justify-between">
              <div>
                <div className="text-xs uppercase tracking-[0.24em] text-white/40">Execution Ledger</div>
                <div className="text-lg font-semibold">Trade evidence cards</div>
              </div>
            </div>
            <div className="grid gap-4 md:grid-cols-2">
              {trades.length === 0 ? (
                <div className="rounded-2xl border border-dashed border-white/10 bg-black/20 p-5 text-sm text-white/45">
                  Executed trades will populate here with thesis, catalyst, and approval state.
                </div>
              ) : (
                trades.slice(0, 8).map((trade) => <TradeCard key={trade.id} trade={trade} />)
              )}
            </div>
          </div>

          <div className={`${PANEL} p-5`}>
            <div className="mb-4 flex items-center justify-between">
              <div>
                <div className="text-xs uppercase tracking-[0.24em] text-white/40">Portfolio Snapshot</div>
                <div className="text-lg font-semibold">Fund state</div>
              </div>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="rounded-2xl bg-black/20 p-4 text-sm text-white/68">Cash {formatCurrency(portfolio?.cash ?? 0)}</div>
              <div className="rounded-2xl bg-black/20 p-4 text-sm text-white/68">
                Realized {formatCurrency(portfolio?.realized_pnl ?? 0)}
              </div>
              <div className="rounded-2xl bg-black/20 p-4 text-sm text-white/68">
                Unrealized {formatCurrency(portfolio?.unrealized_pnl ?? 0)}
              </div>
              <div className="rounded-2xl bg-black/20 p-4 text-sm text-white/68">
                Active scenario {controlState.active_scenario ?? "none"}
              </div>
            </div>

            <div className="mt-4 space-y-3">
              {(portfolio?.positions ?? []).map((position) => (
                <div key={position.asset} className="rounded-2xl border border-white/8 bg-white/[0.03] p-4">
                  <div className="mb-2 flex items-center justify-between">
                    <div className="text-sm font-semibold text-white">{position.asset}</div>
                    <div className={position.unrealized_pnl >= 0 ? "text-emerald-200" : "text-red-200"}>
                      {formatCurrency(position.unrealized_pnl)}
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-2 text-sm text-white/62">
                    <div className="rounded-xl bg-black/20 p-2">Qty {position.quantity.toFixed(3)}</div>
                    <div className="rounded-xl bg-black/20 p-2">Avg {formatCurrency(position.average_cost)}</div>
                    <div className="rounded-xl bg-black/20 p-2">Last {formatCurrency(position.current_price)}</div>
                    <div className="rounded-xl bg-black/20 p-2">Weight {(position.weight * 100).toFixed(1)}%</div>
                  </div>
                </div>
              ))}
            </div>

            {sessionSummary ? (
              <div className="mt-5 rounded-[24px] border border-[#4DD6C0]/25 bg-[#4DD6C0]/8 p-5">
                <div className="text-xs uppercase tracking-[0.24em] text-[#d9fff7]/65">Session Summary</div>
                <div className="mt-2 text-2xl font-semibold text-white">{sessionSummary.headline}</div>
                <div className="mt-3 grid gap-3 sm:grid-cols-2">
                  <div className="rounded-2xl bg-black/20 p-3 text-sm text-white/70">
                    Final NAV {formatCurrency(sessionSummary.total_value)}
                  </div>
                  <div className="rounded-2xl bg-black/20 p-3 text-sm text-white/70">
                    Total return {formatPercent(sessionSummary.total_return_pct)}
                  </div>
                  <div className="rounded-2xl bg-black/20 p-3 text-sm text-white/70">
                    Top agent {sessionSummary.top_agent ?? "n/a"}
                  </div>
                  <div className="rounded-2xl bg-black/20 p-3 text-sm text-white/70">
                    Trades {sessionSummary.trade_count}
                  </div>
                </div>
              </div>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}
