from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.auth import get_current_user_id
from app.database import get_user_identity


router = APIRouter(prefix="/users", tags=["users"])


class CurrentUserResponse(BaseModel):
    id: UUID
    email: str | None
    provider: str


@router.get("/me", response_model=CurrentUserResponse)
def get_me(
    user_id: Annotated[UUID, Depends(get_current_user_id)],
) -> CurrentUserResponse:
    user = get_user_identity(user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return CurrentUserResponse.model_validate(user)
