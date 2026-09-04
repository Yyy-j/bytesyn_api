from fastapi import FastAPI, HTTPException, status

from app.auth import router as auth_router
from app.database import check_database
from app.users import router as users_router


app = FastAPI(title="BYTESYNC API")
app.include_router(auth_router)
app.include_router(users_router)


@app.get("/health")
def health() -> dict[str, object]:
    try:
        database_is_healthy = check_database()
    except (KeyError, TypeError, ValueError, OSError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable",
        ) from None
    except Exception:
        # Database driver failures are intentionally hidden from the client.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable",
        ) from None

    if not database_is_healthy:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable",
        )

    return {"status": "ok", "database": True}
