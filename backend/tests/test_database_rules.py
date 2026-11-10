"""Rules the code relies on, enforced by the database too (0054): orders without
two items in one place, a portfolio video's file registered once, support
accounts without a password, and email batches closed exactly when done."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from backend.identity.models import User
from backend.notifications.models import (
    BatchState,
    DeliveryStatus,
    NotificationBatch,
    NotificationDelivery,
)
from backend.portfolio.models import (
    PortfolioEntry,
    PortfolioPhoto,
    PortfolioSection,
    PortfolioVideo,
    VideoType,
)
from backend.projects.enums import CoverType
from backend.proposals.models import ProposalServicePreset
from backend.tests.test_project_models import add_project
from backend.tests.test_tenancy_models import add_tenant, assert_refused

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 11, 10, 9, 0, tzinfo=UTC)


@pytest.fixture
async def alinea(db_session):
    return await add_tenant(db_session, "alinea")


@pytest.fixture
async def norte(db_session):
    return await add_tenant(db_session, "norte", "Estúdio Norte")


async def checked_now(session):
    """Deferred rules are checked at commit; this checks them at once."""
    await session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))


def entry(tenant, position):
    return PortfolioEntry(
        tenant_id=tenant.id, position=position, title="", place="", description="", credits=""
    )


def photo(tenant, work, position, file_id=None):
    return PortfolioPhoto(
        tenant_id=tenant.id,
        entry_id=work.id,
        position=position,
        file_id=file_id or f"foto-{position}",
        image_type=CoverType.JPEG,
    )


def video(tenant, work, position, file_id=None):
    return PortfolioVideo(
        tenant_id=tenant.id,
        entry_id=work.id,
        position=position,
        file_id=file_id or f"video-{position}",
        video_type=VideoType.MP4,
        poster_file_id=f"capa-{position}",
        poster_type=CoverType.JPEG,
    )


async def a_work(session, tenant, position=1):
    work = entry(tenant, position)
    session.add(work)
    await session.flush()
    return work


# -- orders: one item per place, swapped freely within one change ---------------


async def test_two_portfolio_sections_never_share_a_place(db_session, alinea, norte):
    db_session.add_all(
        [
            PortfolioSection(tenant_id=alinea.id, position=1, label="Casas", slug="casas"),
            PortfolioSection(tenant_id=norte.id, position=1, label="Casas", slug="casas"),
        ]
    )
    await db_session.flush()  # each office has its own order
    db_session.add(PortfolioSection(tenant_id=alinea.id, position=1, label="Lojas", slug="lojas"))
    await db_session.flush()
    await assert_refused(
        db_session, checked_now(db_session), "uq_portfolio_sections_tenant_id_position"
    )


async def test_two_portfolio_pieces_never_share_a_place(db_session, alinea, norte):
    await a_work(db_session, alinea)
    await a_work(db_session, norte)  # each office has its own order
    db_session.add(entry(alinea, 1))
    await db_session.flush()
    await assert_refused(
        db_session, checked_now(db_session), "uq_portfolio_entries_tenant_id_position"
    )


async def test_every_piece_moves_down_a_place_in_one_change(db_session, alinea):
    """New pieces come first: all the others move one place down in one statement,
    passing through duplicates, which only the end result must be free of."""
    for position in (1, 2, 3):
        await a_work(db_session, alinea, position)
    await db_session.execute(text("UPDATE portfolio_entries SET position = position + 1"))
    db_session.add(entry(alinea, 1))
    await db_session.flush()
    await checked_now(db_session)  # no error


async def test_two_photos_of_a_piece_never_share_a_place(db_session, alinea):
    first, second = await a_work(db_session, alinea, 1), await a_work(db_session, alinea, 2)
    db_session.add_all([photo(alinea, first, 1), photo(alinea, second, 1)])
    await db_session.flush()  # each piece has its own order
    db_session.add(photo(alinea, first, 1, "foto-outra"))
    await db_session.flush()
    await assert_refused(
        db_session, checked_now(db_session), "uq_portfolio_photos_entry_id_position"
    )


async def test_two_videos_of_a_piece_never_share_a_place(db_session, alinea):
    first, second = await a_work(db_session, alinea, 1), await a_work(db_session, alinea, 2)
    db_session.add_all([video(alinea, first, 1), video(alinea, second, 1, "video-b")])
    await db_session.flush()  # each piece has its own order
    db_session.add(video(alinea, first, 1, "video-c"))
    await db_session.flush()
    await assert_refused(
        db_session, checked_now(db_session), "uq_portfolio_videos_entry_id_position"
    )


async def test_two_proposal_services_never_share_a_place(db_session, alinea, norte):
    def service(tenant, title):
        return ProposalServicePreset(tenant_id=tenant.id, position=1, title=title, description="")

    db_session.add_all([service(alinea, "Projeto"), service(norte, "Projeto")])
    await db_session.flush()  # each office has its own order
    db_session.add(service(alinea, "Obra"))
    await db_session.flush()
    await assert_refused(
        db_session, checked_now(db_session), "uq_proposal_service_presets_tenant_id_position"
    )


# -- a portfolio video's file -----------------------------------------------------


async def test_a_video_file_is_registered_once(db_session, alinea, norte):
    """Removing one of two rows sharing a file would trash the file the other plays."""
    first, second = await a_work(db_session, alinea, 1), await a_work(db_session, alinea, 2)
    db_session.add(video(alinea, first, 1, "drive-file-1"))
    await db_session.flush()
    norte_work = await a_work(db_session, norte)
    db_session.add(video(norte, norte_work, 1, "drive-file-1"))  # another office's storage
    await db_session.flush()
    db_session.add(video(alinea, second, 1, "drive-file-1"))
    await assert_refused(db_session, db_session.flush(), "uq_portfolio_videos_tenant_id_file_id")


# -- support accounts (A43) -------------------------------------------------------


async def test_a_support_account_never_has_a_password(db_session, alinea):
    db_session.add(
        User(tenant_id=alinea.id, email="ana@alinea.example", name="Ana", password_hash="h")
    )
    await db_session.flush()  # an ordinary account may
    db_session.add(
        User(
            tenant_id=alinea.id,
            email="suporte@unio.invalid",
            name="Suporte Unio",
            support=True,
            password_hash="h",
        )
    )
    await assert_refused(db_session, db_session.flush(), "ck_users_support_without_password")


# -- email batches (A12) ------------------------------------------------------------


async def a_batch(session, tenant, **values):
    project = await add_project(session, tenant)
    fields = {
        "tenant_id": tenant.id,
        "project_id": project.id,
        "first_event_at": NOW - timedelta(minutes=50),
        "last_event_at": NOW - timedelta(minutes=10),
    } | values
    batch = NotificationBatch(**fields)
    session.add(batch)
    await session.flush()
    return batch


@pytest.mark.parametrize(
    ("state", "closed"),
    [
        (BatchState.OPEN, True),
        (BatchState.SENDING, True),
        (BatchState.SENT, False),
        (BatchState.DROPPED, False),
    ],
)
async def test_a_batch_is_closed_exactly_when_sent_or_dropped(db_session, alinea, state, closed):
    await assert_refused(
        db_session,
        a_batch(db_session, alinea, state=state, closed_at=NOW if closed else None),
        "ck_notification_batches_closed_when_done",
    )


@pytest.mark.parametrize("state", list(BatchState))
async def test_a_batch_in_each_state_is_kept_with_its_closing(db_session, alinea, state):
    done = state in (BatchState.SENT, BatchState.DROPPED)
    await a_batch(db_session, alinea, state=state, closed_at=NOW if done else None)  # no error


async def test_a_batchs_last_change_never_comes_before_its_first(db_session, alinea):
    await assert_refused(
        db_session,
        a_batch(db_session, alinea, first_event_at=NOW, last_event_at=NOW - timedelta(seconds=1)),
        "ck_notification_batches_events_in_order",
    )


async def test_a_delivery_never_counts_fewer_than_no_attempts(db_session, alinea):
    batch = await a_batch(db_session, alinea)
    db_session.add(
        NotificationDelivery(
            tenant_id=alinea.id,
            batch_id=batch.id,
            email="cliente@exemplo.com.br",
            status=DeliveryStatus.PENDING,
            attempts=-1,
        )
    )
    await assert_refused(
        db_session, db_session.flush(), "ck_notification_deliveries_attempts_not_negative"
    )
