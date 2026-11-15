"""FastAPI endpoints for Data Connectors, schema discovery, migration preparation, and sync history.

Strict Scope:
- Neon PostgreSQL (predefined, primary database, migration source)
- MongoDB (register multiple connections, document/collection discovery)
- SharePoint (Microsoft Graph API OAuth, site/library/file discovery, ingestion staging)
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.schemas.connectors import (
    ConnectionTestResult,
    ConnectorDiscoveryResult,
    ConnectorSummary,
    DataPreviewResponse,
    MigrationPlanRequest,
    MigrationPreviewResponse,
    MongoDBConnectorCreate,
    MongoDBConnectorUpdate,
    SharePointConnectorCreate,
    SharePointConnectorUpdate,
    SharePointIngestionPrepareRequest,
    SharePointIngestionPrepareResponse,
    SyncHistoryResponse,
)
from app.services.connector_service import ConnectorService, get_connector_service

router = APIRouter()


@router.get("", response_model=List[ConnectorSummary], summary="List all data connectors")
async def list_connectors(
    service: ConnectorService = Depends(get_connector_service),
) -> List[ConnectorSummary]:
    """Retrieve all available and connected data connectors with credentials securely masked."""
    return service.get_all_connectors()


@router.get("/{connector_id}", response_model=ConnectorSummary, summary="Get connector details")
async def get_connector(
    connector_id: str,
    service: ConnectorService = Depends(get_connector_service),
) -> ConnectorSummary:
    """Retrieve details of a single connector by ID."""
    connector = service.get_connector(connector_id)
    if not connector:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Connector '{connector_id}' not found.",
        )
    return connector


@router.post("/mongodb", response_model=ConnectorSummary, status_code=status.HTTP_201_CREATED, summary="Register MongoDB connector")
async def create_mongodb_connector(
    payload: MongoDBConnectorCreate,
    service: ConnectorService = Depends(get_connector_service),
) -> ConnectorSummary:
    """Register a new MongoDB connection. Credentials are stored securely and masked on return."""
    try:
        return service.create_mongodb_connector(payload)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.put("/mongodb/{connector_id}", response_model=ConnectorSummary, summary="Update MongoDB connector")
async def update_mongodb_connector(
    connector_id: str,
    payload: MongoDBConnectorUpdate,
    service: ConnectorService = Depends(get_connector_service),
) -> ConnectorSummary:
    """Update connection settings for an existing MongoDB connector."""
    try:
        return service.update_mongodb_connector(connector_id, payload)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"MongoDB connector '{connector_id}' not found.")
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/sharepoint", response_model=ConnectorSummary, status_code=status.HTTP_201_CREATED, summary="Register SharePoint connector")
async def create_sharepoint_connector(
    payload: SharePointConnectorCreate,
    service: ConnectorService = Depends(get_connector_service),
) -> ConnectorSummary:
    """Register SharePoint connection using Microsoft Graph API OAuth credentials."""
    try:
        return service.create_sharepoint_connector(payload)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.put("/sharepoint/{connector_id}", response_model=ConnectorSummary, summary="Update SharePoint connector")
async def update_sharepoint_connector(
    connector_id: str,
    payload: SharePointConnectorUpdate,
    service: ConnectorService = Depends(get_connector_service),
) -> ConnectorSummary:
    """Update SharePoint connection parameters."""
    try:
        return service.update_sharepoint_connector(connector_id, payload)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"SharePoint connector '{connector_id}' not found.")
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.delete("/{connector_id}", summary="Delete connector")
async def delete_connector(
    connector_id: str,
    service: ConnectorService = Depends(get_connector_service),
) -> dict:
    """Delete a registered MongoDB or SharePoint connector. Neon PostgreSQL primary connector cannot be deleted."""
    try:
        service.delete_connector(connector_id)
        return {"status": "success", "message": f"Connector '{connector_id}' successfully removed."}
    except ValueError as val_err:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(val_err))
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Connector '{connector_id}' not found.")


@router.post("/{connector_id}/test", response_model=ConnectionTestResult, summary="Test connector connectivity")
async def test_connector(
    connector_id: str,
    service: ConnectorService = Depends(get_connector_service),
) -> ConnectionTestResult:
    """Test connectivity to the specified connector and return roundtrip latency and diagnostics."""
    try:
        return service.test_connection(connector_id)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Connector '{connector_id}' not found.")
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.get("/{connector_id}/discover", response_model=ConnectorDiscoveryResult, summary="Discover schemas, collections, or files")
async def discover_connector_resources(
    connector_id: str,
    service: ConnectorService = Depends(get_connector_service),
) -> ConnectorDiscoveryResult:
    """Introspect tables for Neon PostgreSQL, collections for MongoDB, or document libraries/files for SharePoint."""
    try:
        return service.discover_schema(connector_id)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Connector '{connector_id}' not found.")
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.get("/{connector_id}/preview", response_model=DataPreviewResponse, summary="Preview sample data")
async def preview_data(
    connector_id: str,
    entity_name: str = Query(..., description="Table name, collection name, or file ID"),
    entity_type: str = Query("table", description="'table', 'collection', or 'file'"),
    service: ConnectorService = Depends(get_connector_service),
) -> DataPreviewResponse:
    """Preview sample rows or documents from the selected table, collection, or SharePoint file."""
    try:
        return service.preview_data(connector_id, entity_name, entity_type)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Connector '{connector_id}' not found.")
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.post("/migration/preview", response_model=MigrationPreviewResponse, summary="Generate migration preview & conflict analysis")
async def preview_migration(
    payload: MigrationPlanRequest,
    service: ConnectorService = Depends(get_connector_service),
) -> MigrationPreviewResponse:
    """
    Generate migration mapping preview and identify incompatible data and schema conflicts.
    Execution is strictly gated; bulk data transfer is deferred to a future task.
    """
    try:
        return service.preview_migration(payload)
    except KeyError as k_err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(k_err))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/sharepoint/prepare-ingestion", response_model=SharePointIngestionPrepareResponse, summary="Prepare SharePoint file for ingestion")
async def prepare_sharepoint_ingestion(
    payload: SharePointIngestionPrepareRequest,
    service: ConnectorService = Depends(get_connector_service),
) -> SharePointIngestionPrepareResponse:
    """Validate discovered SharePoint file and prepare it for ingestion into the platform pipeline."""
    try:
        return service.prepare_sharepoint_ingestion(payload)
    except KeyError as k_err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(k_err))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/sync-history/list", response_model=SyncHistoryResponse, summary="Get synchronization history")
async def get_sync_history(
    limit: int = Query(50, ge=1, le=200),
    service: ConnectorService = Depends(get_connector_service),
) -> SyncHistoryResponse:
    """Retrieve synchronization, discovery, and test history with error details."""
    return service.get_sync_history(limit=limit)

