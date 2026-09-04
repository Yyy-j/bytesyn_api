from fastapi import FastAPI, HTTPException, status

from app.auth import router as auth_router
from app.db import get_connection
from app.users import router as users_router

app = FastAPI(title="BYTESYNC API")
app.include_router(auth_router)
app.include_router(users_router)


@app.get("/health")
def health() -> dict[str, object]:
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                row = cursor.fetchone()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable",
        ) from None

    if row is None or next(iter(row.values())) != 1:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable",
        )
    return {"status": "ok", "database": True}
