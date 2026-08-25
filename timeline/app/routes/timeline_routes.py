"""Timeline prediction API routes."""

from typing import Any

from fastapi import APIRouter, HTTPException, status

from app.models.schemas import (
    TimelinePredictionResponse,
)
from app.services.timeline_service import generate_timeline_prediction


router = APIRouter(
    prefix="/api/timeline",
    tags=["Project Management & Timeline Prediction"],
)


@router.post(
    "/predict",
    response_model=TimelinePredictionResponse,
    status_code=status.HTTP_200_OK,
)
def predict_timeline(
    request: dict[str, Any],
) -> TimelinePredictionResponse:
    """Generate planned construction timeline prediction."""

    try:
        prediction = generate_timeline_prediction(request)
        return TimelinePredictionResponse(**prediction)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Prediction service failed: {exc}",
        ) from exc


@router.post(
    "/performance-format",
    status_code=status.HTTP_200_OK,
)
def predict_timeline_performance_format(
    request: dict[str, Any],
) -> dict[str, Any]:
    """Generate only the planned schedule payload for the downstream component."""

    try:
        prediction = generate_timeline_prediction(request)
        return prediction["performance_monitoring_payload"]
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Downstream planned schedule payload generation failed: {exc}",
        ) from exc
