from contextlib import asynccontextmanager
import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from config import settings
from db.mongo import init_mongo, close_mongo
from db.firebase_admin import init_firebase
from db.indexes import create_indexes

limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    init_mongo()
    init_firebase()
    create_indexes()

    # Start background workers
    from workers.anomaly_detector import run_worker
    from workers.escalation_scheduler import run_scheduler
    asyncio.create_task(run_worker())
    asyncio.create_task(run_scheduler())

    yield
    close_mongo()


app = FastAPI(
    title="Maharashtra Tourist Safety API",
    version="1.0.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ────────────────────────────────────────────────────────────────────
from routers import identity, location, sos, zones, score, incidents, blockchain, tourists

app.include_router(identity.router,   prefix=settings.API_V1_PREFIX)
app.include_router(location.router,   prefix=settings.API_V1_PREFIX)
app.include_router(sos.router,        prefix=settings.API_V1_PREFIX)
app.include_router(zones.router,      prefix=settings.API_V1_PREFIX)
app.include_router(score.router,      prefix=settings.API_V1_PREFIX)
app.include_router(incidents.router,  prefix=settings.API_V1_PREFIX)
app.include_router(blockchain.router, prefix=settings.API_V1_PREFIX)
app.include_router(tourists.router,   prefix=settings.API_V1_PREFIX)


@app.get("/health", tags=["health"])
async def health_check():
    return JSONResponse({"status": "ok", "version": "1.0.0"})
