import math
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from psycopg import IntegrityError

from app.auth import get_current_user_id
from app.db import connection


router = APIRouter(prefix="/users/me", tags=["body"])

SexForEnergyEstimate = Literal["male", "female"]
ActivityLevel = Literal["sedentary", "light", "moderate", "high", "very_high"]
Direction = Literal["lose", "maintain", "gain"]

BodyHeight = Annotated[Decimal, Field(ge=100, le=250, max_digits=6, decimal_places=2)]
BodyWeight = Annotated[Decimal, Field(ge=20, le=400, max_digits=6, decimal_places=2)]
GoalCalories = Annotated[Decimal, Field(ge=0, le=10000, max_digits=7, decimal_places=2)]
GoalMacro = Annotated[Decimal, Field(ge=0, le=1000, max_digits=6, decimal_places=2)]

ACTIVITY_MULTIPLIERS: dict[str, Decimal] = {
    "sedentary": Decimal("1.2"),
    "light": Decimal("1.375"),
    "moderate": Decimal("1.55"),
    "high": Decimal("1.725"),
    "very_high": Decimal("1.9"),
}
RECOMMENDATION_METHOD = "mifflin_st_jeor_v1"
KCAL_PER_KG = Decimal("7700")
MAINTAIN_TOLERANCE_KG = Decimal("0.1")
MAX_LOSS_BODY_WEIGHT_PER_WEEK = Decimal("0.01")
MAX_DAILY_DEFICIT_TDEE_RATIO = Decimal("0.25")
MAX_GAIN_BODY_WEIGHT_PER_WEEK = Decimal("0.005")
MAX_DAILY_SURPLUS_TDEE_RATIO = Decimal("0.15")
MIN_CALORIES_BY_SEX = {"male": Decimal("1500"), "female": Decimal("1200")}


def _today() -> date:
    return date.today()


def _one_decimal(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def _two_decimals(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _whole(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _bmi(weight_kg: Decimal, height_cm: Decimal) -> float:
    metres = height_cm / Decimal(100)
    return _one_decimal(weight_kg / (metres * metres))


def _validate_birth_year(value: int, today: date) -> None:
    if value < 1900 or value > today.year:
        raise ValueError("birth_year must be between 1900 and the current year")


def _validate_target_date(value: date, today: date) -> None:
    if value < today:
        raise ValueError("target_date must not be in the past")


def _invalid_authentication() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid authentication credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


class WeightMeasurementResponse(BaseModel):
    id: UUID
    measured_on: date
    weight_kg: float
    height_cm_snapshot: float
    bmi: float
    created_at: datetime
    updated_at: datetime


class WeightMeasurementListResponse(BaseModel):
    measurements: list[WeightMeasurementResponse]


class CreateWeightMeasurement(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    measured_on: date
    weight_kg: BodyWeight

    @model_validator(mode="after")
    def reject_future_date(self):
        if self.measured_on > _today():
            raise ValueError("measured_on must not be in the future")
        return self


class PatchWeightMeasurement(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    measured_on: date | None = None
    weight_kg: BodyWeight | None = None

    @model_validator(mode="after")
    def require_change(self):
        if not self.model_fields_set:
            raise ValueError("at least one field is required")
        if any(getattr(self, name) is None for name in self.model_fields_set):
            raise ValueError("weight measurement fields cannot be null")
        if "measured_on" in self.model_fields_set and self.measured_on > _today():
            raise ValueError("measured_on must not be in the future")
        return self


class CurrentWeightResponse(BaseModel):
    measurement_id: UUID
    measured_on: date
    weight_kg: float
    bmi: float


class BodyDataResponse(BaseModel):
    height_cm: float | None
    current_weight: CurrentWeightResponse | None
    target_weight_kg: float | None
    target_date: date | None
    weight_difference_kg: float | None


class RecommendationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    birth_year: int
    sex_for_energy_estimate: SexForEnergyEstimate
    height_cm: BodyHeight
    current_weight_kg: BodyWeight
    target_weight_kg: BodyWeight
    target_date: date
    activity_level: ActivityLevel

    @model_validator(mode="after")
    def validate_dates(self):
        today = _today()
        _validate_birth_year(self.birth_year, today)
        _validate_target_date(self.target_date, today)
        if self.target_date == today and (
            abs(self.target_weight_kg - self.current_weight_kg)
            > MAINTAIN_TOLERANCE_KG
        ):
            raise ValueError("target_date must be in the future for weight change")
        return self


class RecommendedGoals(BaseModel):
    calories: int
    protein: int
    carbs: int
    fat: int


class RecommendationResponse(BaseModel):
    method: str
    direction: Direction
    bmr: int
    maintenance_calories: int
    recommended_calories: int
    requested_target_date: date
    recommended_target_date: date
    aggressive_timeline: bool
    recommended_goals: RecommendedGoals


class OnboardingGoals(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    calories: GoalCalories
    protein: GoalMacro
    carbs: GoalMacro
    fat: GoalMacro


class SavedGoals(BaseModel):
    calories: float
    protein: float
    carbs: float
    fat: float


class OnboardingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    birth_year: int
    sex_for_energy_estimate: SexForEnergyEstimate
    height_cm: BodyHeight
    current_weight_kg: BodyWeight
    target_weight_kg: BodyWeight
    target_date: date
    activity_level: ActivityLevel
    goals: OnboardingGoals

    @model_validator(mode="after")
    def validate_dates(self):
        today = _today()
        _validate_birth_year(self.birth_year, today)
        _validate_target_date(self.target_date, today)
        return self


class OnboardingResponse(BaseModel):
    onboarding_completed_at: datetime
    birth_year: int
    sex_for_energy_estimate: SexForEnergyEstimate
    height_cm: float
    target_weight_kg: float
    target_date: date
    activity_level: ActivityLevel
    goals: SavedGoals
    current_weight: WeightMeasurementResponse


def _measurement_response(row: dict[str, object]) -> WeightMeasurementResponse:
    return WeightMeasurementResponse(
        **row,
        bmi=_bmi(row["weight_kg"], row["height_cm_snapshot"]),
    )


def calculate_recommendation(body: RecommendationRequest) -> RecommendationResponse:
    today = _today()
    age = today.year - body.birth_year
    # With birth year alone, a difference of exactly 18 cannot prove that the
    # birthday has already occurred. Stay conservative instead of estimating
    # for someone who may still be 17.
    if age <= 18:
        raise HTTPException(
            status_code=422,
            detail="Birth year does not confirm an age of 18 or older",
        )

    sex_offset = Decimal(5) if body.sex_for_energy_estimate == "male" else Decimal(-161)
    bmr = (
        Decimal(10) * body.current_weight_kg
        + Decimal("6.25") * body.height_cm
        - Decimal(5) * Decimal(age)
        + sex_offset
    )
    tdee = bmr * ACTIVITY_MULTIPLIERS[body.activity_level]
    difference = body.target_weight_kg - body.current_weight_kg
    days = max((body.target_date - today).days, 1)
    requested_daily_change = abs(difference) * KCAL_PER_KG / Decimal(days)

    if abs(difference) <= MAINTAIN_TOLERANCE_KG:
        direction: Direction = "maintain"
        recommended = tdee
        aggressive = False
        recommended_date = body.target_date
        protein_factor = Decimal("1.6")
    elif difference < 0:
        direction = "lose"
        weekly_weight_cap = body.current_weight_kg * MAX_LOSS_BODY_WEIGHT_PER_WEEK
        daily_weight_cap = weekly_weight_cap * KCAL_PER_KG / Decimal(7)
        calorie_floor = MIN_CALORIES_BY_SEX[body.sex_for_energy_estimate]
        allowed_change = max(
            Decimal(0),
            min(
                daily_weight_cap,
                tdee * MAX_DAILY_DEFICIT_TDEE_RATIO,
                tdee - calorie_floor,
            ),
        )
        applied_change = min(requested_daily_change, allowed_change)
        recommended = max(calorie_floor, tdee - applied_change)
        aggressive = requested_daily_change > allowed_change
        safe_days = (
            math.ceil(float(abs(difference) * KCAL_PER_KG / allowed_change))
            if aggressive and allowed_change > 0
            else days
        )
        recommended_date = today + timedelta(days=safe_days)
        protein_factor = Decimal("1.8")
    else:
        direction = "gain"
        weekly_weight_cap = body.current_weight_kg * MAX_GAIN_BODY_WEIGHT_PER_WEEK
        daily_weight_cap = weekly_weight_cap * KCAL_PER_KG / Decimal(7)
        allowed_change = min(
            daily_weight_cap,
            tdee * MAX_DAILY_SURPLUS_TDEE_RATIO,
        )
        applied_change = min(requested_daily_change, allowed_change)
        recommended = max(
            MIN_CALORIES_BY_SEX[body.sex_for_energy_estimate],
            tdee + applied_change,
        )
        aggressive = requested_daily_change > allowed_change
        safe_days = (
            math.ceil(float(abs(difference) * KCAL_PER_KG / allowed_change))
            if aggressive and allowed_change > 0
            else days
        )
        recommended_date = today + timedelta(days=safe_days)
        protein_factor = Decimal("1.6")

    calories = _whole(recommended)
    protein = _whole(body.current_weight_kg * protein_factor)
    fat = _whole(Decimal(calories) * Decimal("0.25") / Decimal(9))
    carbs = max(0, _whole(
        (Decimal(calories) - Decimal(protein * 4) - Decimal(fat * 9))
        / Decimal(4)
    ))
    return RecommendationResponse(
        method=RECOMMENDATION_METHOD,
        direction=direction,
        bmr=_whole(bmr),
        maintenance_calories=_whole(tdee),
        recommended_calories=calories,
        requested_target_date=body.target_date,
        recommended_target_date=recommended_date,
        aggressive_timeline=aggressive,
        recommended_goals=RecommendedGoals(
            calories=calories,
            protein=protein,
            carbs=carbs,
            fat=fat,
        ),
    )


@router.get("/weight-measurements", response_model=WeightMeasurementListResponse)
def list_weight_measurements(
    user_id: Annotated[UUID, Depends(get_current_user_id)],
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
) -> WeightMeasurementListResponse:
    with connection() as conn, conn.cursor() as cursor:
        cursor.execute("SELECT 1 FROM users WHERE id = %s", (user_id,))
        if cursor.fetchone() is None:
            raise _invalid_authentication()
        cursor.execute(
            """SELECT id, measured_on, weight_kg, height_cm_snapshot,
                      created_at, updated_at
               FROM weight_measurements
               WHERE user_id = %s
               ORDER BY measured_on DESC, created_at DESC
               LIMIT %s""",
            (user_id, limit),
        )
        return WeightMeasurementListResponse(
            measurements=[_measurement_response(row) for row in cursor.fetchall()]
        )


@router.post(
    "/weight-measurements",
    response_model=WeightMeasurementResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_weight_measurement(
    body: CreateWeightMeasurement,
    user_id: Annotated[UUID, Depends(get_current_user_id)],
) -> WeightMeasurementResponse:
    try:
        with connection() as conn, conn.cursor() as cursor:
            cursor.execute("SELECT height_cm FROM users WHERE id = %s", (user_id,))
            user = cursor.fetchone()
            if user is None:
                raise _invalid_authentication()
            if user["height_cm"] is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Height is required before recording weight",
                )
            cursor.execute(
                """INSERT INTO weight_measurements
                       (user_id, measured_on, weight_kg, height_cm_snapshot)
                   VALUES (%s, %s, %s, %s)
                   RETURNING id, measured_on, weight_kg, height_cm_snapshot,
                             created_at, updated_at""",
                (user_id, body.measured_on, body.weight_kg, user["height_cm"]),
            )
            return _measurement_response(cursor.fetchone())
    except IntegrityError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A weight measurement already exists for this date",
        ) from error


@router.patch(
    "/weight-measurements/{measurement_id}",
    response_model=WeightMeasurementResponse,
)
def patch_weight_measurement(
    measurement_id: UUID,
    body: PatchWeightMeasurement,
    user_id: Annotated[UUID, Depends(get_current_user_id)],
) -> WeightMeasurementResponse:
    try:
        with connection() as conn, conn.cursor() as cursor:
            cursor.execute(
                """SELECT id FROM weight_measurements
                   WHERE id = %s AND user_id = %s FOR UPDATE""",
                (measurement_id, user_id),
            )
            if cursor.fetchone() is None:
                raise HTTPException(status_code=404, detail="Weight measurement not found")
            changes = body.model_dump(exclude_unset=True)
            assignments = ", ".join(f"{column} = %s" for column in changes)
            cursor.execute(
                f"""UPDATE weight_measurements SET {assignments}
                    WHERE id = %s AND user_id = %s
                    RETURNING id, measured_on, weight_kg, height_cm_snapshot,
                              created_at, updated_at""",
                [*changes.values(), measurement_id, user_id],
            )
            return _measurement_response(cursor.fetchone())
    except IntegrityError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A weight measurement already exists for this date",
        ) from error


@router.delete(
    "/weight-measurements/{measurement_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_weight_measurement(
    measurement_id: UUID,
    user_id: Annotated[UUID, Depends(get_current_user_id)],
) -> Response:
    with connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            "DELETE FROM weight_measurements WHERE id = %s AND user_id = %s RETURNING id",
            (measurement_id, user_id),
        )
        if cursor.fetchone() is None:
            raise HTTPException(status_code=404, detail="Weight measurement not found")
        return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/body", response_model=BodyDataResponse)
def get_body_data(
    user_id: Annotated[UUID, Depends(get_current_user_id)],
) -> BodyDataResponse:
    with connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            "SELECT height_cm, target_weight_kg, target_date FROM users WHERE id = %s",
            (user_id,),
        )
        user = cursor.fetchone()
        if user is None:
            raise _invalid_authentication()
        cursor.execute(
            """SELECT id, measured_on, weight_kg, height_cm_snapshot
               FROM weight_measurements WHERE user_id = %s
               ORDER BY measured_on DESC, created_at DESC LIMIT 1""",
            (user_id,),
        )
        latest = cursor.fetchone()
        current = None
        difference = None
        if latest is not None:
            current = CurrentWeightResponse(
                measurement_id=latest["id"],
                measured_on=latest["measured_on"],
                weight_kg=float(latest["weight_kg"]),
                bmi=_bmi(latest["weight_kg"], latest["height_cm_snapshot"]),
            )
            if user["target_weight_kg"] is not None:
                difference = _two_decimals(
                    user["target_weight_kg"] - latest["weight_kg"]
                )
        return BodyDataResponse(
            height_cm=user["height_cm"],
            current_weight=current,
            target_weight_kg=user["target_weight_kg"],
            target_date=user["target_date"],
            weight_difference_kg=difference,
        )


@router.post("/calorie-recommendation", response_model=RecommendationResponse)
def calorie_recommendation(
    body: RecommendationRequest,
    user_id: Annotated[UUID, Depends(get_current_user_id)],
) -> RecommendationResponse:
    with connection() as conn:
        if conn.execute("SELECT 1 FROM users WHERE id = %s", (user_id,)).fetchone() is None:
            raise _invalid_authentication()
    return calculate_recommendation(body)


@router.post("/onboarding", response_model=OnboardingResponse)
def complete_onboarding(
    body: OnboardingRequest,
    user_id: Annotated[UUID, Depends(get_current_user_id)],
) -> OnboardingResponse:
    measured_on = _today()
    with connection() as conn, conn.cursor() as cursor:
        cursor.execute("SELECT id FROM users WHERE id = %s FOR UPDATE", (user_id,))
        if cursor.fetchone() is None:
            raise _invalid_authentication()
        cursor.execute(
            """UPDATE users SET
                   birth_year = %s,
                   sex_for_energy_estimate = %s,
                   height_cm = %s,
                   target_weight_kg = %s,
                   target_date = %s,
                   activity_level = %s,
                   calorie_goal = %s,
                   protein_goal = %s,
                   carbs_goal = %s,
                   fat_goal = %s,
                   onboarding_completed_at = COALESCE(onboarding_completed_at, now())
               WHERE id = %s
               RETURNING onboarding_completed_at""",
            (
                body.birth_year,
                body.sex_for_energy_estimate,
                body.height_cm,
                body.target_weight_kg,
                body.target_date,
                body.activity_level,
                body.goals.calories,
                body.goals.protein,
                body.goals.carbs,
                body.goals.fat,
                user_id,
            ),
        )
        completed_at = cursor.fetchone()["onboarding_completed_at"]
        cursor.execute(
            """INSERT INTO weight_measurements
                   (user_id, measured_on, weight_kg, height_cm_snapshot)
               VALUES (%s, %s, %s, %s)
               ON CONFLICT (user_id, measured_on) DO UPDATE SET
                   weight_kg = EXCLUDED.weight_kg,
                   height_cm_snapshot = EXCLUDED.height_cm_snapshot
               RETURNING id, measured_on, weight_kg, height_cm_snapshot,
                         created_at, updated_at""",
            (user_id, measured_on, body.current_weight_kg, body.height_cm),
        )
        measurement = _measurement_response(cursor.fetchone())
        return OnboardingResponse(
            onboarding_completed_at=completed_at,
            birth_year=body.birth_year,
            sex_for_energy_estimate=body.sex_for_energy_estimate,
            height_cm=float(body.height_cm),
            target_weight_kg=float(body.target_weight_kg),
            target_date=body.target_date,
            activity_level=body.activity_level,
            goals=SavedGoals(**{
                name: float(value) for name, value in body.goals.model_dump().items()
            }),
            current_weight=measurement,
        )
