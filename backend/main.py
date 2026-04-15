"""
main.py — FastAPI application entry point
"""
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.database import init_db
from backend.routes import telemetry, predictions, agent, control


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: create all DB tables
    await init_db()
    yield
    # Shutdown: nothing to clean up


app = FastAPI(
    title="AIoT Smart Energy Intelligence Platform",
    description="AI + Deep Learning powered Smart Prepaid Energy Meter backend",
    version="2.0.0",
    lifespan=lifespan,
)

# ── CORS (allow React dev server) ─────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(telemetry.router)
app.include_router(predictions.router)
app.include_router(agent.router)
app.include_router(control.router)


@app.get("/")
async def root():
    return {
        "name":    "AIoT Smart Energy Platform",
        "version": "2.0.0",
        "status":  "running",
        "docs":    "/docs",
    }


@app.get("/health")
async def health():
    return {"status": "healthy"}
