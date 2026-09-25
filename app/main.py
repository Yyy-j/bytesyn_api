import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from psycopg import Error as PsycopgError

from app.auth import router as auth_router
from app.ai_meals import router as ai_meals_router
from app.pairs import router as pairs_router
from app.meals import router as meals_router
from app.users import router as users_router
from app.summary import router as summary_router
from app.training import router as training_router
from app.training_exercises import router as training_exercises_router

logger = logging.getLogger("uvicorn.error")


def _allowed_origins() -> list[str]:
    """Return explicit browser origins without enabling a wildcard."""
    return [
        origin.strip().rstrip("/")
        for origin in os.environ.get("ALLOWED_ORIGINS", "").split(",")
        if origin.strip()
    ]


@asynccontextmanager
async def lifespan(_: FastAPI):
    # The Docker entrypoint is intentionally interface-agnostic. Uvicorn also
    # emits its effective address; this concise line is easy to find in logs.
    logger.info("Server listening: 0.0.0.0:8000")
    yield


app = FastAPI(title="BYTESYNC API", lifespan=lifespan)
allowed_origins = _allowed_origins()
if allowed_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(pairs_router)
app.include_router(meals_router)
app.include_router(summary_router)
app.include_router(ai_meals_router)
app.include_router(training_router)
app.include_router(training_exercises_router)


@app.exception_handler(PsycopgError)
def database_error_handler(_, __):
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": "Database unavailable"},
    )


@app.get("/health")
def health() -> dict[str, object]:
    # This endpoint is a network/process liveness check. Keep the existing
    # response contract, but do not make reachability depend on PostgreSQL.
    return {"status": "ok", "database": True}
