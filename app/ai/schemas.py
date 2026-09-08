from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
Nutrition = Annotated[float, Field(strict=True, ge=0, allow_inf_nan=False)]


class AnalyzeTextRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


class DishEstimate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: Name
    calories: Nutrition


class MealEstimate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: Name
    calories: Nutrition
    protein: Nutrition
    carbs: Nutrition
    fat: Nutrition
    dishes: list[DishEstimate] = Field(min_length=1, max_length=50)


class AnalyzeTextResponse(MealEstimate):
    source: Literal['text'] = 'text'
