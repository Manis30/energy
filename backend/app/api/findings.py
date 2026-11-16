"""Operational Energy Findings Lifecycle API endpoints."""

from datetime import datetime
import json
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.models.findings import OperationalFinding
from app.schemas.findings import (
    AcknowledgeFindingRequest,
    AddNotesRequest,
    FindingDetailResponse,
    FindingListResponse,
    FindingSummary,
    OccurrenceProvenanceResponse,
    ReopenFindingRequest,
    ResolveFindingRequest,
    StartInvestigationRequest,
    SyncFindingsRequest,
    SyncFindingsResponse,
)
from app.services.finding_lifecycle_service import (
    acknowledge_finding,
    add_investigation_notes,
    get_finding_detail,
    get_occurrence_provenance,
    list_findings,
    reopen_finding,
    resolve_finding,
    start_investigation,
    sync_findings_from_anomalies,
)

router = APIRouter()


def _to_summary_dict(f: OperationalFinding) -> Dict[str, Any]:
    """Serialize OperationalFinding model to summary dictionary."""
    summary: Dict[str, Any] = {
        "finding_id": f.finding_id,
        "finding_key": f.finding_key,
        "anomaly_type": f.anomaly_type,
        "plant_id": f.plant_id,
        "meter_id": f.meter_id,
        "line_id": f.line_id,
        "status": f.status,
        "severity": f.severity,
        "occurrence_count": f.occurrence_count,
        "first_detected_at": f.first_detected_at.isoformat() if f.first_detected_at else "",
        "last_detected_at": f.last_detected_at.isoformat() if f.last_detected_at else "",
        "current_actual_value": f.current_actual_value,
        "current_baseline_value": f.current_baseline_value,
        "current_deviation_score": f.current_deviation_score,
        "current_explanation": f.current_explanation,
        "acknowledged_at": f.acknowledged_at.isoformat() if f.acknowledged_at else None,
        "investigated_at": f.investigated_at.isoformat() if f.investigated_at else None,
        "resolved_at": f.resolved_at.isoformat() if f.resolved_at else None,
        "reopened_at": f.reopened_at.isoformat() if f.reopened_at else None,
        "created_at": f.created_at.isoformat() if f.created_at else "",
        "updated_at": f.updated_at.isoformat() if f.updated_at else "",
        "latest_source_table": None,
        "latest_source_record_id": None,
        "latest_upload_id": None,
        "latest_detector_version": None,
        "latest_lineage_status": None,
    }
    if hasattr(f, "occurrences") and f.occurrences:
        latest = f.occurrences[0]
        c_flags = {}
        if latest.context_flags_json:
            try:
                c_flags = json.loads(latest.context_flags_json)
            except Exception:
                c_flags = {}
        summary["latest_source_table"] = latest.source_table
        summary["latest_source_record_id"] = latest.source_record_id
        summary["latest_upload_id"] = latest.upload_id
        summary["latest_detector_version"] = latest.detector_version
        if latest.source_table and latest.source_record_id:
            summary["latest_lineage_status"] = "AVAILABLE"
        elif c_flags.get("source_records"):
            summary["latest_lineage_status"] = c_flags.get("lineage_status", "MULTI_SOURCE")
        else:
            summary["latest_lineage_status"] = "UNAVAILABLE"

    return summary


def _to_detail_dict(f: OperationalFinding) -> Dict[str, Any]:
    """Serialize OperationalFinding model with full occurrences and audit trail."""
    data = _to_summary_dict(f)
    data["investigation_notes"] = f.investigation_notes
    data["resolution_notes"] = f.resolution_notes
    data["reopen_reason"] = f.reopen_reason

    occurrences_data = []
    for occ in (f.occurrences or []):
        c_flags = {}
        if occ.context_flags_json:
            try:
                c_flags = json.loads(occ.context_flags_json)
            except Exception:
                c_flags = {}

        if occ.source_table and occ.source_record_id:
            lineage_status = "AVAILABLE"
            source_records = c_flags.get("source_records") or [
                {
                    "source_table": occ.source_table,
                    "source_record_id": occ.source_record_id,
                    "upload_id": occ.upload_id,
                }
            ]
        elif c_flags.get("source_records"):
            lineage_status = c_flags.get("lineage_status", "MULTI_SOURCE")
            source_records = c_flags.get("source_records", [])
        else:
            lineage_status = "UNAVAILABLE"
            source_records = []

        occurrences_data.append({
            "occurrence_id": occ.occurrence_id,
            "finding_id": occ.finding_id,
            "occurrence_ts": occ.occurrence_ts.isoformat() if occ.occurrence_ts else "",
            "actual_value": occ.actual_value,
            "baseline_value": occ.baseline_value,
            "deviation_score": occ.deviation_score,
            "severity": occ.severity,
            "explanation": occ.explanation,
            "context_flags": c_flags,
            "recorded_at": occ.recorded_at.isoformat() if occ.recorded_at else "",
            "source_table": occ.source_table,
            "source_record_id": occ.source_record_id,
            "upload_id": occ.upload_id,
            "detector_version": occ.detector_version,
            "lineage_status": lineage_status,
            "source_records": source_records,
        })

    data["occurrences"] = occurrences_data

    if occurrences_data:
        latest = occurrences_data[0]
        data["latest_source_table"] = latest.get("source_table")
        data["latest_source_record_id"] = latest.get("source_record_id")
        data["latest_upload_id"] = latest.get("upload_id")
        data["latest_detector_version"] = latest.get("detector_version")
        data["latest_lineage_status"] = latest.get("lineage_status")

    audit_trail: List[Dict[str, Any]] = []
    for a in (f.audit_logs or []):
        meta: Dict[str, Any] = {}
        if a.audit_metadata_json:
            try:
                meta = json.loads(a.audit_metadata_json)
            except Exception:
                meta = {}
        audit_trail.append({
            "id": a.id,
            "action": a.action,
            "from_status": a.from_status,
            "to_status": a.to_status,
            "performed_at": a.performed_at.isoformat() if a.performed_at else "",
            "comment": a.comment,
            "actor_attribution": meta.get("actor_attribution"),
            "actor_type": meta.get("actor_type", "UNVERIFIED_CALLER"),
            "metadata": meta.get("details", {}),
        })
    data["audit_trail"] = audit_trail
    return data


@router.get(
    "",
    response_model=FindingListResponse,
    summary="List operational findings",
    description="Retrieve paginated operational findings with status, severity, plant, and meter filters.",
)
def read_findings(
    plant_id: Optional[str] = Query(None, description="Filter by plant ID, e.g. 'IN-TN-01'"),
    meter_id: Optional[str] = Query(None, description="Filter by meter ID, e.g. 'MTR-SMT'"),
    line_id: Optional[str] = Query(None, description="Filter by line ID, e.g. 'SMT-L1'"),
    status: Optional[str] = Query(None, description="Filter by status: 'NEW', 'ACKNOWLEDGED', 'INVESTIGATING', 'RESOLVED', 'REOPENED', or 'ACTIVE'"),
    severity: Optional[str] = Query(None, description="Filter by severity: 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFORMATIONAL'"),
    anomaly_type: Optional[str] = Query(None, description="Filter by anomaly category or detector family identifier"),
    search: Optional[str] = Query(None, description="Database-wide partial text search across finding_id, plant_id, meter_id, line_id, and anomaly_type"),
    limit: int = Query(50, ge=1, le=500, description="Page limit (default 50, max 500)"),
    offset: int = Query(0, ge=0, description="Page offset (default 0)"),
    db: Session = Depends(get_db_session),
) -> FindingListResponse:
    try:
        items, total = list_findings(
            session=db,
            plant_id=plant_id,
            meter_id=meter_id,
            line_id=line_id,
            status=status,
            severity=severity,
            anomaly_type=anomaly_type,
            search=search,
            limit=limit,
            offset=offset,
        )
        return FindingListResponse(
            items=[FindingSummary(**_to_summary_dict(f)) for f in items],
            total=total,
            limit=limit,
            offset=offset,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve operational findings: {str(e)}",
        )


@router.get(
    "/{finding_id}",
    response_model=FindingDetailResponse,
    summary="Get operational finding detail",
    description="Retrieve full finding lifecycle state, immutable detection occurrences evidence, and transition audit trail.",
)
def read_finding_detail(
    finding_id: str,
    db: Session = Depends(get_db_session),
) -> FindingDetailResponse:
    finding = get_finding_detail(db, finding_id)
    if not finding:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Finding '{finding_id}' not found.",
        )
    return FindingDetailResponse(**_to_detail_dict(finding))


@router.get(
    "/{finding_id}/occurrences/{occurrence_id}/provenance",
    response_model=OccurrenceProvenanceResponse,
    summary="Get source record provenance for a specific occurrence",
    description="Retrieve end-to-end read-only provenance drill-down from finding occurrence down to physical source rows and batch upload audit records.",
)
def read_occurrence_provenance(
    finding_id: str,
    occurrence_id: str,
    db: Session = Depends(get_db_session),
) -> OccurrenceProvenanceResponse:
    try:
        prov = get_occurrence_provenance(session=db, finding_id=finding_id, occurrence_id=occurrence_id)
        return OccurrenceProvenanceResponse(**prov)
    except KeyError as ke:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ke))
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ve))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve occurrence provenance: {str(e)}",
        )


@router.get(
    "/{finding_id}/provenance",
    response_model=OccurrenceProvenanceResponse,
    summary="Get source record provenance for finding (latest or specified occurrence)",
    description="Retrieve end-to-end read-only provenance drill-down defaulting to the latest occurrence if occurrence_id is omitted.",
)
def read_finding_provenance(
    finding_id: str,
    occurrence_id: Optional[str] = Query(None, description="Optional occurrence ID to inspect. If omitted, defaults to latest occurrence."),
    db: Session = Depends(get_db_session),
) -> OccurrenceProvenanceResponse:
    try:
        prov = get_occurrence_provenance(session=db, finding_id=finding_id, occurrence_id=occurrence_id)
        return OccurrenceProvenanceResponse(**prov)
    except KeyError as ke:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ke))
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ve))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve finding provenance: {str(e)}",
        )


@router.post(
    "/{finding_id}/acknowledge",
    response_model=FindingDetailResponse,
    summary="Acknowledge operational finding",
    description="Transition finding status from NEW or REOPENED to ACKNOWLEDGED with optional operator comment and caller attribution.",
)
def acknowledge_finding_endpoint(
    finding_id: str,
    payload: AcknowledgeFindingRequest,
    db: Session = Depends(get_db_session),
) -> FindingDetailResponse:
    try:
        finding = acknowledge_finding(
            session=db,
            finding_id=finding_id,
            comment=payload.comment,
            caller_attribution=payload.caller_attribution,
        )
        detailed = get_finding_detail(db, finding.finding_id)
        return FindingDetailResponse(**_to_detail_dict(detailed or finding))
    except KeyError as ke:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ke))
    except ValueError as ve:
        err_msg = str(ve)
        status_code = status.HTTP_409_CONFLICT if "Invalid finding status transition" in err_msg else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_code, detail=err_msg)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to acknowledge finding: {str(e)}",
        )


@router.post(
    "/{finding_id}/investigate",
    response_model=FindingDetailResponse,
    summary="Start investigation on finding",
    description="Transition finding status from NEW, ACKNOWLEDGED, or REOPENED to INVESTIGATING.",
)
def investigate_finding_endpoint(
    finding_id: str,
    payload: StartInvestigationRequest,
    db: Session = Depends(get_db_session),
) -> FindingDetailResponse:
    try:
        finding = start_investigation(
            session=db,
            finding_id=finding_id,
            investigation_notes=payload.investigation_notes,
            caller_attribution=payload.caller_attribution,
        )
        detailed = get_finding_detail(db, finding.finding_id)
        return FindingDetailResponse(**_to_detail_dict(detailed or finding))
    except KeyError as ke:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ke))
    except ValueError as ve:
        err_msg = str(ve)
        status_code = status.HTTP_409_CONFLICT if "Invalid finding status transition" in err_msg else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_code, detail=err_msg)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start investigation on finding: {str(e)}",
        )


@router.post(
    "/{finding_id}/notes",
    response_model=FindingDetailResponse,
    summary="Add investigation notes",
    description="Append timestamped investigation diagnostic notes to finding without altering lifecycle status.",
)
def add_finding_notes_endpoint(
    finding_id: str,
    payload: AddNotesRequest,
    db: Session = Depends(get_db_session),
) -> FindingDetailResponse:
    try:
        finding = add_investigation_notes(
            session=db,
            finding_id=finding_id,
            notes=payload.notes,
            caller_attribution=payload.caller_attribution,
        )
        detailed = get_finding_detail(db, finding.finding_id)
        return FindingDetailResponse(**_to_detail_dict(detailed or finding))
    except KeyError as ke:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ke))
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to add notes to finding: {str(e)}",
        )


@router.post(
    "/{finding_id}/resolve",
    response_model=FindingDetailResponse,
    summary="Resolve operational finding",
    description="Transition finding status from ACKNOWLEDGED, INVESTIGATING, or REOPENED to RESOLVED with mandatory resolution notes.",
)
def resolve_finding_endpoint(
    finding_id: str,
    payload: ResolveFindingRequest,
    db: Session = Depends(get_db_session),
) -> FindingDetailResponse:
    try:
        finding = resolve_finding(
            session=db,
            finding_id=finding_id,
            resolution_notes=payload.resolution_notes,
            caller_attribution=payload.caller_attribution,
        )
        detailed = get_finding_detail(db, finding.finding_id)
        return FindingDetailResponse(**_to_detail_dict(detailed or finding))
    except KeyError as ke:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ke))
    except ValueError as ve:
        err_msg = str(ve)
        status_code = status.HTTP_409_CONFLICT if "Invalid finding status transition" in err_msg else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_code, detail=err_msg)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to resolve finding: {str(e)}",
        )


@router.post(
    "/{finding_id}/reopen",
    response_model=FindingDetailResponse,
    summary="Manually reopen a resolved finding",
    description="Transition finding status from RESOLVED to REOPENED with documented engineering justification.",
)
def reopen_finding_endpoint(
    finding_id: str,
    payload: ReopenFindingRequest,
    db: Session = Depends(get_db_session),
) -> FindingDetailResponse:
    try:
        finding = reopen_finding(
            session=db,
            finding_id=finding_id,
            reason=payload.reason,
            caller_attribution=payload.caller_attribution,
        )
        detailed = get_finding_detail(db, finding.finding_id)
        return FindingDetailResponse(**_to_detail_dict(detailed or finding))
    except KeyError as ke:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ke))
    except ValueError as ve:
        err_msg = str(ve)
        status_code = status.HTTP_409_CONFLICT if "Invalid finding status transition" in err_msg else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_code, detail=err_msg)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reopen finding: {str(e)}",
        )


@router.post(
    "/sync",
    response_model=SyncFindingsResponse,
    summary="Synchronize findings from anomaly detection",
    description="Run deterministic anomaly detection and synchronize deduplicated findings, occurrence evidence, and recurrence states.",
)
def sync_findings_endpoint(
    payload: SyncFindingsRequest = SyncFindingsRequest(),
    db: Session = Depends(get_db_session),
) -> SyncFindingsResponse:
    try:
        start_dt = datetime.fromisoformat(payload.start_time.replace("Z", "+00:00")) if payload.start_time else None
        end_dt = datetime.fromisoformat(payload.end_time.replace("Z", "+00:00")) if payload.end_time else None
        result = sync_findings_from_anomalies(
            session=db,
            plant_id=payload.plant_id,
            meter_id=payload.meter_id,
            start_time=start_dt,
            end_time=end_dt,
            caller_attribution=payload.caller_attribution,
        )
        return SyncFindingsResponse(**result)
    except RuntimeError as re:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(re),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to synchronize findings from anomaly detection: {str(e)}",
        )
