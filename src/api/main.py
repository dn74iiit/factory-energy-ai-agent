"""
FastAPI Application implementing the Mandatory API Contract (Section 6).
Endpoints:
- POST /analyze: natural language question decomposition & plans
- POST /ingest: live multipart data ingestion
- GET /health: system readiness check
- GET /trace/{run_id}: audit execution record
- GET /validation: dataset validation report
"""

import os
from typing import Optional
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from src.api.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    IngestResponse,
    HealthResponse,
    TraceResponse
)
from src.agent.graph import run_agent
from src.agent.tracer import audit_tracer
from src.database import db
from data.loader import load_csv
from data.validate_data import validate_dataset
from src.config import DATA_DIR, LLM_PROVIDER, MOCK_LLM

app = FastAPI(
    title="Factory Energy Cost Decomposition and Savings Agent API",
    description="HCLTech AI Engineer Hackathon - Production Energy Analytics & Decomposition System",
    version="1.0.0"
)

# Enable CORS for Streamlit / React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health", response_model=HealthResponse)
def get_health():
    """System health and readiness probe."""
    try:
        counts = db.get_counts()
        db_status = "connected"
    except Exception as e:
        db_status = f"error: {str(e)}"
        counts = {}

    llm_status = "ready" if (MOCK_LLM or LLM_PROVIDER in ("groq", "gemini", "openai", "anthropic", "ollama")) else "unconfigured"

    return HealthResponse(
        status="healthy",
        database=db_status,
        llm=llm_status,
        tables=counts
    )

@app.post("/analyze", response_model=AnalyzeResponse)
def post_analyze(req: AnalyzeRequest):
    """
    Analyzes question or request.
    Produces additive cost bridge decomposition, top users, or ranked actions.
    """
    try:
        result = run_agent(
            question=req.question,
            period=req.period or "2026-Q3",
            compare_to=req.compare_to or "2026-Q2"
        )
        return AnalyzeResponse(**result)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Analysis pipeline error: {str(e)}"
        )

@app.post("/ingest", response_model=IngestResponse)
async def post_ingest(
    file: UploadFile = File(...),
    table: str = Form(..., description="Target table: meter_15min, tariff, production, weather")
):
    """
    Adds data while running.
    Multipart form-data: CSV file + table name string.
    Returns rows_loaded, rows_rejected, and status.
    """
    valid_tables = ["meter_15min", "tariff", "production", "weather"]
    if table not in valid_tables:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid table '{table}'. Must be one of {valid_tables}"
        )

    try:
        content = await file.read()
        loaded, rejected, stat_msg = load_csv(table_name=table, file_source=content, replace=True)
        return IngestResponse(
            rows_loaded=loaded,
            rows_rejected=rejected,
            status=stat_msg
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ingestion failed: {str(e)}"
        )

@app.get("/trace/{run_id}", response_model=TraceResponse)
def get_trace(run_id: str):
    """Retrieves execution audit trace by run_id (Annex C format)."""
    trace = audit_tracer.get_trace(run_id)
    if not trace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Trace record not found for run_id '{run_id}'"
        )
    return TraceResponse(**trace)

@app.get("/validation")
def get_validation():
    """Runs Section 4.5 dataset validation checks and returns report."""
    results = validate_dataset(str(DATA_DIR), tolerance_pct=7.0)
    return results

@app.get("/decomposition")
def get_decomposition(period: str = "2026-Q3", compare_to: str = "2026-Q2"):
    """Cost decomposition between periods."""
    from src.analytics.decomposition import decomposition_engine
    return decomposition_engine.decompose(period=period, compare_to=compare_to)

@app.get("/diagnostics/assets")
def get_diagnostics_assets(period: str = "2026-Q3"):
    """Asset energy breakdown from sub-meters."""
    from src.analytics.idle_waste import diagnostic_engine
    return diagnostic_engine.get_asset_breakdown(period=period)

@app.get("/diagnostics/leak")
def get_diagnostics_leak(period: str = "2026-Q3"):
    """Compressor air leak detection."""
    from src.analytics.idle_waste import diagnostic_engine
    return diagnostic_engine.detect_compressor_leak(period=period)

@app.get("/diagnostics/idle")
def get_diagnostics_idle(period: str = "2026-Q3"):
    """Idle power and non-production load analysis."""
    from src.analytics.idle_waste import diagnostic_engine
    return diagnostic_engine.analyze_idle_load(period=period)

@app.get("/recommendations")
def get_recommendations(period: str = "2026-Q3"):
    """Prescriptive actions ranked by payback."""
    from src.analytics.recommendations import recommendation_engine
    return recommendation_engine.generate_recommendations(period=period)

@app.get("/simulate/tariff")
def simulate_tariff(period: str = "2026-Q3"):
    """What-if simulation for tariff reversion."""
    from src.analytics.what_if import what_if_simulator
    return what_if_simulator.simulate_tariff_reversion(period=period)

@app.get("/simulate/leak")
def simulate_leak(period: str = "2026-Q3"):
    """What-if simulation for compressor leak repair."""
    from src.analytics.what_if import what_if_simulator
    return what_if_simulator.simulate_leak_repair(period=period)

@app.get("/simulate/custom")
def simulate_custom(
    period: str = "2026-Q3",
    tariff_delta_pct: float = 0.0,
    volume_delta_pct: float = 0.0,
    repair_leak: bool = False
):
    """Custom dynamic what-if simulation."""
    from src.analytics.what_if import what_if_simulator
    return what_if_simulator.simulate_custom(
        period=period,
        tariff_delta_pct=tariff_delta_pct,
        volume_delta_pct=volume_delta_pct,
        repair_leak=repair_leak
    )

if __name__ == "__main__":
    import uvicorn
    from src.config import API_HOST, API_PORT
    uvicorn.run("src.api.main:app", host=API_HOST, port=API_PORT, reload=False)
