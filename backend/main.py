from fastapi import BackgroundTasks, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from models import AgentControlRequest, OverrideRequest, ScenarioRequest, StartRequest
from trading_loop import sim, trading_loop
from websocket_server import manager

app = FastAPI(title="TradeAgent API")


def dump_model(model):
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/trade/start")
async def start_trade(req: StartRequest, background_tasks: BackgroundTasks):
    if sim.session_active:
        raise HTTPException(status_code=409, detail="A session is already running.")

    if req.scenario and req.scenario not in {scenario["id"] for scenario in sim.get_scenarios()}:
        raise HTTPException(status_code=404, detail="Scenario not found.")

    sim.start(req.capital, req.risk)
    if req.scenario:
        sim.apply_scenario(req.scenario)

    background_tasks.add_task(trading_loop, req.duration)
    return {
        "status": "started",
        "duration": req.duration,
        "capital": req.capital,
        "risk": sim.risk,
        "scenario": sim.active_scenario,
    }


@app.get("/portfolio")
async def get_portfolio():
    return dump_model(sim.get_portfolio_snapshot())


@app.get("/trades")
async def get_trades():
    return [dump_model(trade) for trade in sim.trades]


@app.get("/benchmarks")
async def get_benchmarks():
    return sim.get_benchmark_payload()


@app.get("/research")
async def get_research():
    return sim.latest_research_brief


@app.get("/backtests/lab")
async def get_backtest_lab():
    return sim.run_backtest_lab()


@app.get("/scenarios")
async def get_scenarios():
    return sim.get_scenarios()


@app.post("/scenario/apply")
async def apply_scenario(req: ScenarioRequest):
    scenario = sim.apply_scenario(req.scenario)
    if scenario is None:
        raise HTTPException(status_code=404, detail="Scenario not found.")
    await manager.broadcast({"type": "scenario_update", "data": {"active_scenario": sim.active_scenario}})
    await manager.broadcast(
        {
            "type": "news_update",
            "data": [{"title": headline, "time": ""} for headline in scenario["headlines"]],
        }
    )
    return {"status": "applied", "scenario": scenario}


@app.get("/agents/leaderboard")
async def get_leaderboard():
    return sim.get_leaderboard()


@app.get("/state")
async def get_state():
    return sim.get_session_state()


@app.post("/control/override")
async def set_override(req: OverrideRequest):
    sim.set_override(req.enabled)
    await manager.broadcast({"type": "control_state", "data": sim.get_session_state()})
    return {"status": "ok", "override_active": sim.override_active}


@app.post("/control/agent")
async def set_agent_control(req: AgentControlRequest):
    if not sim.set_agent_paused(req.agent, req.paused):
        raise HTTPException(status_code=404, detail="Agent not found.")
    await manager.broadcast({"type": "control_state", "data": sim.get_session_state()})
    return {"status": "ok", "agent": req.agent, "paused": req.paused}


@app.websocket("/ws/stream")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    await manager.broadcast({"type": "control_state", "data": sim.get_session_state()})
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
