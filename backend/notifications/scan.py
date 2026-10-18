"""The maintenance pass's scan (A10, plan section 13): files a project's page
shows for the first time become "file published" records (A28).

For the pilot this lists each published project's stage folders, as the client
page does, rather than reading Drive's changes feed (Fabio, 16 Oct 2026): a
couple of hundred Drive calls a pass at a handful of offices, and nothing to
miss. A project's first scan only notes what is there, so files from before
never email. A project is written to only when something changed: its
`updated_at` versions the cover's address, which a quiet pass must not move.

One scan of a project at a time: each takes a PostgreSQL advisory lock for that
project, released when its transaction ends, so two passes that overlap (the
scheduler firing again, or someone running the command) skip each other's
project instead of recording its files twice. Nothing holds a connection for the
whole pass.
"""

from __future__ import annotations

import logging
import random
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.db.isolation import scope_to_tenant
from backend.notifications import digest
from backend.notifications.email import EmailSender
from backend.notifications.events import CLIENT_VISIBLE, record
from backend.notifications.models import (
    EventKind,
    MaintenanceRun,
    NotificationBatch,
    ProjectFileSeen,
)
from backend.notifications.office import office_of
from backend.projects.models import Project, ProjectStage
from backend.storage.base import StorageError, StorageProblem
from backend.tenancy.models import Tenant, TenantStatus
from backend.web.page_files import _in_project, stage_groups, storage_view

log = logging.getLogger(__name__)

MAINTENANCE_LOCK = 7_202_611  # next to the migrations' (backend/migrations/registry.py)
_LOCK_PROJECT = text("SELECT pg_try_advisory_xact_lock(:key, hashtext(:project))")


@dataclass
class Report:
    offices: int = 0
    projects: int = 0
    new_files: int = 0
    failed: int = 0  # projects whose folders couldn't be read: logged, tried next pass
    busy: int = 0  # being scanned by another pass just then
    emails: int = 0
    unfinished: int = 0  # not reached before the time budget ran out: the next pass


class Busy(Exception):
    """Another pass is scanning this project."""


async def scan_project(db: AsyncSession, storage, project: Project) -> int:
    """Record the files shown for the first time; how many (0 on a first scan).
    The caller holds the project's lock and commits."""
    folders = (
        await db.execute(
            select(ProjectStage.position, ProjectStage.folder_id)
            .where(ProjectStage.project_id == project.id, ProjectStage.folder_id.is_not(None))
            .order_by(ProjectStage.position)
        )
    ).all()
    inside = await _in_project(storage, project)  # a folder moved away shows nothing
    shown = {}
    for position, folder in folders:
        if folder not in inside:
            continue
        for _group, _listed, files in await stage_groups(storage, folder):
            for item in files:
                # Its identity, not its id: a local file renamed or moved, or its
                # stage folder renamed, is not new (section 14).
                shown.setdefault(item.identity, (position, item))
    seen = set(
        await db.scalars(
            select(ProjectFileSeen.item_id).where(ProjectFileSeen.project_id == project.id)
        )
    )
    new = [found for item_id, found in shown.items() if item_id not in seen]
    first = project.files_scanned_at is None
    if not new and not first:
        return 0
    now = datetime.now(UTC)
    for position, item in new:
        db.add(ProjectFileSeen(project_id=project.id, item_id=item.identity))
        if not first:
            name = f"{item.name}.pdf" if item.is_native else item.name  # as the page names it
            record(
                db,
                project,
                EventKind.FILE_PUBLISHED,
                stage_position=position,
                item_id=item.identity,  # what the email finds it by, renamed or not
                title=name,
            )
    values: dict = {"files_scanned_at": project.files_scanned_at or now}
    if new and not first:
        values["last_activity_at"] = now  # "Atualizado" (A28)
    await db.execute(update(Project).where(Project.id == project.id).values(**values))
    return 0 if first else len(new)


async def _project_pass(db, settings, sender, storage, office, project, report) -> None:
    """One project, under its lock, in one transaction: its new files, then its
    email if one is due."""
    if not await db.scalar(_LOCK_PROJECT, {"key": MAINTENANCE_LOCK, "project": str(project.id)}):
        raise Busy
    if project.status not in CLIENT_VISIBLE:
        # Archived (or back to draft) while an email waited: it is never sent,
        # even if the project comes back later (section 14).
        await digest.drop_unsent(db, project)
        await db.commit()
        return
    if storage is not None and project.folder_id is not None:
        report.new_files += await scan_project(db, storage, project)
    now = datetime.now(UTC)
    # Batches that came due, or are being retried, go as they were: changes made
    # after start the next one, with its own quiet period (section 14).
    for due in await digest.to_send(db, project, now) if sender is not None else []:
        try:
            report.emails += await digest.deliver(
                db, settings, sender, storage, office, project, due, now
            )
        except digest.Wait:
            await db.commit()  # a file still changing, or files unreadable: next pass
            return
    await digest.gather(db, project)
    await db.commit()


async def _scan_office(
    sessionmaker, settings, google, sender, tenant_id, report: Report, deadline: float
) -> None:
    async with sessionmaker() as db:
        scope_to_tenant(db.sync_session, tenant_id)
        # Published projects, and any with an email waiting (to drop it if the
        # project was archived meanwhile).
        waiting = select(NotificationBatch.project_id).where(
            NotificationBatch.state.in_(digest.UNSENT)
        )
        project_ids = list(
            await db.scalars(
                select(Project.id).where(
                    Project.deleted_at.is_(None),
                    Project.status.in_(CLIENT_VISIBLE) | Project.id.in_(waiting),
                )
            )
        )
        office = await office_of(db, settings, tenant_id) if project_ids else None
    report.offices += 1
    random.shuffle(project_ids)  # if passes keep running out of time, not always the same last
    for index, project_id in enumerate(project_ids):
        if time.monotonic() >= deadline:
            report.unfinished += len(project_ids) - index
            return
        report.projects += 1
        # Its own session: a project that fails leaves the others' work alone.
        async with sessionmaker() as db:
            scope_to_tenant(db.sync_session, tenant_id)
            try:
                # None without Drive: meetings and stages still email.
                storage = await storage_view(db, settings, google)
                project = await db.scalar(select(Project).where(Project.id == project_id))
                if project is not None:
                    await _project_pass(db, settings, sender, storage, office, project, report)
            except Busy:
                report.busy += 1
            except StorageError as error:
                await db.rollback()
                report.failed += 1
                # A folder that is gone is the office's doing, seen every pass: a
                # warning. Drive failing is ours to look at: an error (AGENTS.md).
                gone = error.problem in (StorageProblem.NOT_FOUND, StorageProblem.NO_ACCESS)
                log.log(
                    logging.WARNING if gone else logging.ERROR,
                    "maintenance: scanning files of %s/%s failed: %s %s",
                    tenant_id,
                    project_id,
                    error.problem,
                    error.detail,
                )


async def run_maintenance(
    sessionmaker: async_sessionmaker[AsyncSession],
    settings,
    google,
    sender: EmailSender | None = None,
    budget: float | None = None,
) -> Report:
    """One pass over every active office: new files, then the emails that are due
    (none without a `sender`). With a `budget` in seconds, no new project starts
    after it: each project's work is saved as it finishes, and the rest is the
    next pass's (section 4: bounded work)."""
    async with sessionmaker() as db:
        offices = list(
            await db.scalars(select(Tenant.id).where(Tenant.status == TenantStatus.ACTIVE))
        )
    report = Report()
    deadline = time.monotonic() + budget if budget is not None else float("inf")
    random.shuffle(offices)
    for tenant_id in offices:
        await _scan_office(sessionmaker, settings, google, sender, tenant_id, report, deadline)
    log.info("maintenance: %s", report)
    await _record(sessionmaker, report)
    return report


async def _record(sessionmaker, report: Report) -> None:
    """When it ran, and when it last ran to the end (plan section 4)."""
    now = datetime.now(UTC)
    # Every project done by this pass: none left, failed, or held by another pass.
    complete = not (report.unfinished or report.failed or report.busy)
    values = {"last_run_at": now, "last_report": asdict(report)}
    async with sessionmaker() as db:
        await db.execute(
            insert(MaintenanceRun)
            .values(id=1, last_success_at=now if complete else None, **values)
            .on_conflict_do_update(
                index_elements=[MaintenanceRun.id],
                set_=values | ({"last_success_at": now} if complete else {}),
            )
        )
        await db.commit()
