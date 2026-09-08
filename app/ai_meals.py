from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError

from app.auth import get_current_user_id
from app.ai.gemini_provider import AIUnavailable, TextMealProvider, get_text_meal_provider
from app.ai.schemas import AnalyzeTextRequest, AnalyzeTextResponse, MealEstimate

router = APIRouter(prefix='/ai/meals', tags=['ai-meals'])


@router.post('/analyze-text', response_model=AnalyzeTextResponse)
def analyze_text(
    body: AnalyzeTextRequest,
    user_id: Annotated[UUID, Depends(get_current_user_id)],
    provider: Annotated[TextMealProvider, Depends(get_text_meal_provider)],
) -> AnalyzeTextResponse:
    try:
        raw = provider.analyze_text(body.text)
    except AIUnavailable:
        raise HTTPException(503, 'AI service unavailable') from None
    except Exception:
        raise HTTPException(502, 'AI analysis failed') from None
    try:
        estimate = MealEstimate.model_validate_json(raw)
    except (ValidationError, TypeError, ValueError):
        raise HTTPException(502, 'Invalid AI response') from None
    return AnalyzeTextResponse(**estimate.model_dump(), source='text')
