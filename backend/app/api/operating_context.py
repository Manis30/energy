"""API endpoints for Phase 3 Operating Context and Energy Analysis."""

from datetime import date, datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.schemas.common import validate_date_range, validate_time_range
from app.schemas.operating_context import (
    HourlyOperatingObservation,
    OperatingContextSummaryResponse,
    StoppageEpisodeDetailResponse,
    StoppageEpisodesResponse,
)
from app.services.operating_context import (
    detect_stoppage_episodes,
    get_operating_context_observations,
    get_operating_context_summary,
    get_stoppage_episode_detail,
)

router = APIRouter()


@router.get(
    "/summary",
    response_model=OperatingContextSummaryResponse,
    summary="Get Operating Context summary statistics",
    description="Returns observation coverage counts (matched, missing) and stoppage episode aggregates.",
)
def read_operating_context_summary(
    plant_id: Optional[str] = Query(None, description="Plant ID filter, e.g. 'IN-KA-01'"),
    line_id: Optional[str] = Query(None, description="Production line filter, e.g. 'FAL-L2'"),
    start_date: Optional[date] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="End date (YYYY-MM-DD)"),
    db: Session = Depends(get_db_session),
) -> OperatingContextSummaryResponse:
    validate_date_range(start_date, end_date)
    return get_operating_context_summary(
        session=db,
        plant_id=plant_id,
        line_id=line_id,
        start_date=start_date,
        end_date=end_date,
    )


@router.get(
    "/observations",
    response_model=List[HourlyOperatingObservation],
    summary="Get hourly operating observations",
    description="Fetches plant/line/hour observations joining production, energy, machine telemetry, and shift calendar.",
)
def read_operating_observations(
    plant_id: Optional[str] = Query(None, description="Plant ID filter, e.g. 'IN-KA-01'"),
    line_id: Optional[str] = Query(None, description="Production line filter, e.g. 'FAL-L2'"),
    start_date: Optional[date] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="End date (YYYY-MM-DD)"),
    start_time: Optional[datetime] = Query(None, description="Start timestamp filter"),
    end_time: Optional[datetime] = Query(None, description="End timestamp filter"),
    limit: int = Query(5000, ge=1, le=50000, description="Max observations to return"),
    db: Session = Depends(get_db_session),
) -> List[HourlyOperatingObservation]:
    validate_date_range(start_date, end_date)
    validate_time_range(start_time, end_time)
    return get_operating_context_observations(
        session=db,
        plant_id=plant_id,
        line_id=line_id,
        start_date=start_date,
        end_date=end_date,
        start_time=start_time,
        end_time=end_time,
        limit=limit,
    )


@router.get(
    "/stoppages",
    response_model=StoppageEpisodesResponse,
    summary="List detected stoppage episodes",
    description="Identifies consecutive zero-output hours, energy consumed, lost target output, and restart behavior.",
)
def read_stoppage_episodes(
    plant_id: Optional[str] = Query(None, description="Plant ID filter, e.g. 'IN-KA-01'"),
    line_id: Optional[str] = Query(None, description="Production line filter, e.g. 'FAL-L2'"),
    start_date: Optional[date] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="End date (YYYY-MM-DD)"),
    min_duration_hours: int = Query(1, ge=1, description="Minimum episode duration in consecutive hours"),
    downtime_reason: Optional[str] = Query(None, description="Filter by downtime reason, e.g. 'CHANGEOVER'"),
    db: Session = Depends(get_db_session),
) -> StoppageEpisodesResponse:
    validate_date_range(start_date, end_date)
    obs = get_operating_context_observations(
        session=db,
        plant_id=plant_id,
        line_id=line_id,
        start_date=start_date,
        end_date=end_date,
        limit=50000,
    )
    episodes = detect_stoppage_episodes(
        observations=obs,
        min_duration_hours=min_duration_hours,
        downtime_reason=downtime_reason,
    )
    return StoppageEpisodesResponse(
        total_count=len(episodes),
        episodes=episodes,
    )


@router.get(
    "/stoppages/{episode_id}",
    response_model=StoppageEpisodeDetailResponse,
    summary="Get stoppage episode details with similar historical periods",
    description="Fetches a stoppage episode, its constituent hourly readings, and descriptive comparison against historical episodes on the same line.",
)
def read_stoppage_episode_detail(
    episode_id: str,
    db: Session = Depends(get_db_session),
) -> StoppageEpisodeDetailResponse:
    detail = get_stoppage_episode_detail(session=db, episode_id=episode_id)
    if not detail:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Stoppage episode '{episode_id}' not found.",
        )
    return detail


@router.get(
    "/utilities",
    summary="Get qualified utility telemetry observations",
    description="Returns utility telemetry observations (compressed air, chilled water, HVAC, nitrogen, process water). "
                "Distinguishes compressor electricity from delivery flow and pressure. Refuses cross-unit flow aggregation.",
)
def read_utility_telemetry(
    plant_id: str = Query("IN-TN-01", description="Plant ID"),
    utility_type: Optional[str] = Query(None, description="Utility type (e.g. COMPRESSED_AIR, CHILLED_WATER, HVAC, NITROGEN, PROCESS_WATER)"),
    start_time: Optional[datetime] = Query(None, description="Start timestamp"),
    end_time: Optional[datetime] = Query(None, description="End timestamp"),
    equipment_id: Optional[str] = Query(None, description="Equipment identifier"),
    limit: int = Query(50, ge=1, le=500),
    session: Session = Depends(get_db_session),
):
    from app.services.operating_context import get_utility_telemetry_observations
    return get_utility_telemetry_observations(
        session=session,
        plant_id=plant_id,
        utility_type=utility_type,
        start_time=start_time,
        end_time=end_time,
        equipment_id=equipment_id,
        limit=limit,
    )
