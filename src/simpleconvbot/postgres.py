from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, DateTime, Integer, String, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from simpleconvbot.jobs import (
    CreateJob,
    InvalidTransition,
    JobNotFound,
    JobSnapshot,
    JobState,
    ensure_transition,
)


def utc_now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class TelegramUpdateRow(Base):
    __tablename__ = "telegram_updates"

    update_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class JobRow(Base):
    __tablename__ = "jobs"

    job_id: Mapped[UUID] = mapped_column(primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(512), unique=True, index=True)
    operation_id: Mapped[str] = mapped_column(String(128))
    operation_version: Mapped[int] = mapped_column(Integer)
    user_id: Mapped[int] = mapped_column(BigInteger)
    chat_id: Mapped[int] = mapped_column(BigInteger)
    source_message_id: Mapped[int] = mapped_column(BigInteger)
    state: Mapped[str] = mapped_column(String(32), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


def make_engine(database_url: str) -> AsyncEngine:
    return create_async_engine(database_url, pool_pre_ping=True)


def make_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def create_schema(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


async def drop_schema(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)


class PostgresUpdateReceiptStore:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def claim(self, update_id: int) -> bool:
        async with self._sessions() as session:
            session.add(TelegramUpdateRow(update_id=update_id))
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                existing = await session.get(TelegramUpdateRow, update_id)
                if existing is None:
                    raise
                return False
            return True


class PostgresJobRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def create_or_get(self, command: CreateJob) -> tuple[JobSnapshot, bool]:
        async with self._sessions() as session:
            row = JobRow(
                job_id=uuid4(),
                idempotency_key=command.idempotency_key,
                operation_id=command.operation_id,
                operation_version=command.operation_version,
                user_id=command.user_id,
                chat_id=command.chat_id,
                source_message_id=command.source_message_id,
                state=JobState.RECEIVED.value,
            )
            session.add(row)
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                existing = await session.scalar(
                    select(JobRow).where(JobRow.idempotency_key == command.idempotency_key)
                )
                if existing is None:
                    raise
                return _snapshot(existing), False

            await session.refresh(row)
            return _snapshot(row), True

    async def get(self, job_id: UUID) -> JobSnapshot:
        async with self._sessions() as session:
            row = await session.get(JobRow, job_id)
            if row is None:
                raise JobNotFound(str(job_id))
            return _snapshot(row)

    async def transition(
        self,
        job_id: UUID,
        expected: JobState,
        target: JobState,
    ) -> JobSnapshot:
        ensure_transition(expected, target)
        async with self._sessions() as session:
            updated_id = await session.scalar(
                update(JobRow)
                .where(JobRow.job_id == job_id, JobRow.state == expected.value)
                .values(state=target.value, updated_at=utc_now())
                .returning(JobRow.job_id)
            )
            if updated_id is None:
                actual = await session.get(JobRow, job_id)
                if actual is None:
                    raise JobNotFound(str(job_id))
                raise InvalidTransition(JobState(actual.state), target)

            await session.commit()
            row = await session.get(JobRow, job_id)
            if row is None:
                raise JobNotFound(str(job_id))
            return _snapshot(row)


def _snapshot(row: JobRow) -> JobSnapshot:
    return JobSnapshot(
        job_id=row.job_id,
        idempotency_key=row.idempotency_key,
        operation_id=row.operation_id,
        operation_version=row.operation_version,
        user_id=row.user_id,
        chat_id=row.chat_id,
        source_message_id=row.source_message_id,
        state=JobState(row.state),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
