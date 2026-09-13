from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import ValidationError

from app.auth import get_current_user_id
from app.ai.gemini_provider import (
    AIUnavailable, ImageMealProvider, TextMealProvider,
    get_image_meal_provider, get_text_meal_provider,
)
from app.ai.schemas import (
    AnalyzeImageResponse, AnalyzeTextRequest, AnalyzeTextResponse, MealEstimate,
)

router = APIRouter(prefix='/ai/meals', tags=['ai-meals'])
MAX_IMAGE_BYTES = 5 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {'image/jpeg', 'image/png', 'image/webp'}


def valid_image_signature(image_bytes: bytes, mime_type: str) -> bool:
    if mime_type == 'image/jpeg':
        return image_bytes.startswith(b'\xff\xd8\xff')
    if mime_type == 'image/png':
        return image_bytes.startswith(b'\x89PNG\r\n\x1a\n')
    if mime_type == 'image/webp':
        return (len(image_bytes) >= 12 and image_bytes.startswith(b'RIFF')
                and image_bytes[8:12] == b'WEBP')
    return False


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


@router.post('/analyze-image', response_model=AnalyzeImageResponse)
def analyze_image(
    user_id: Annotated[UUID, Depends(get_current_user_id)],
    provider: Annotated[ImageMealProvider, Depends(get_image_meal_provider)],
    image: Annotated[UploadFile, File()],
    hint: Annotated[str | None, Form()] = None,
) -> AnalyzeImageResponse:
    mime_type = (image.content_type or '').lower()
    if mime_type not in ALLOWED_IMAGE_TYPES:
        image.file.close()
        raise HTTPException(400, 'Invalid image format')
    try:
        image_bytes = image.file.read(MAX_IMAGE_BYTES + 1)
    finally:
        image.file.close()
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise HTTPException(413, 'Image too large')
    if not valid_image_signature(image_bytes, mime_type):
        raise HTTPException(400, 'Invalid image format')
    clean_hint = hint.strip() if hint and hint.strip() else None
    try:
        raw = provider.analyze_image(image_bytes, mime_type, clean_hint)
    except AIUnavailable:
        raise HTTPException(503, 'AI service unavailable') from None
    except Exception:
        raise HTTPException(502, 'AI analysis failed') from None
    try:
        estimate = MealEstimate.model_validate_json(raw)
        if len(estimate.dishes) > 10:
            raise ValueError()
    except (ValidationError, TypeError, ValueError):
        raise HTTPException(502, 'Invalid AI response') from None
    return AnalyzeImageResponse(**estimate.model_dump(), source='ai')
