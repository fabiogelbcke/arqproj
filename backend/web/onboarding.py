"""The painel's "first steps": what a new office still has to do.

Worked out from the real state each time, so it can never disagree with it.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.engine import get_tenant_session
from backend.projects.models import Project
from backend.storage.models import ReaderStatus, StorageConnection, StorageKind, WriterStatus
from backend.web.auth import CurrentStaff, current_staff

router = APIRouter(prefix="/api")


class OnboardingOut(BaseModel):
    storage_connected: bool  # where project files live (Google Drive for now)
    has_project: bool


@router.get("/onboarding")
async def onboarding(
    _staff: CurrentStaff = Depends(current_staff), db: AsyncSession = Depends(get_tenant_session)
) -> OnboardingOut:
    connection = await db.scalar(select(StorageConnection))
    # Done only when both paths work: the office's grant (writing) and the reader
    # identity (pages and downloads), plan section 9.
    connected = connection is not None and (
        connection.kind is StorageKind.FOLDER
        or (
            connection.writer_status is WriterStatus.CONNECTED
            and connection.reader_status is ReaderStatus.OK
        )
    )
    has_project = await db.scalar(select(exists().where(Project.deleted_at.is_(None))))
    return OnboardingOut(storage_connected=connected, has_project=bool(has_project))
