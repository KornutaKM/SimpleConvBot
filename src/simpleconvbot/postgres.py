from __future__ import annotations

from datetime import UTC, datetime
from hashlib import blake2b
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    delete,
    func,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from simpleconvbot.jobs import (
    ACTIVE_STATES,
    CreateJob,
    InvalidTransition,
    JobAdmissionCode,
    JobAdmissionPolicy,
    JobAdmissionRejected,
    JobNotFound,
    JobSnapshot,
    JobState,
    ensure_transition,
)
from simpleconvbot.sessions import (
    CollectionSessionSnapshot,
    FinalizedSessionPlan,
    SessionAccessDenied,
    SessionClosed,
    SessionEmpty,
    SessionExpired,
    SessionFileInput,
    SessionFileNotFound,
    SessionFileSnapshot,
    SessionIdempotencyConflict,
    SessionKind,
    SessionLimitExceeded,
    SessionNotFound,
    SessionPolicy,
    SessionState,
    finalization_plan,
)


def utc_now() -> datetime:
    return datetime.now(UTC)


_GLOBAL_JOB_LOCK = int.from_bytes(b"SCBJOBGL", "big", signed=False)


def _user_job_lock(user_id: int) -> int:
    digest = blake2b(
        str(user_id).encode("ascii"),
        digest_size=8,
        person=b"SCBJOB1",
    ).digest()
    return int.from_bytes(digest, "big", signed=True)


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


class CollectionSessionRow(Base):
    __tablename__ = "collection_sessions"

    session_id: Mapped[UUID] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(32))
    state: Mapped[str] = mapped_column(String(32), index=True)
    owner_user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    file_count: Mapped[int] = mapped_column(Integer, default=0)
    total_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class CollectionSessionFileRow(Base):
    __tablename__ = "collection_session_files"
    __table_args__ = (
        UniqueConstraint(
            "session_id",
            "source_message_id",
            name="uq_collection_session_source_message",
        ),
        UniqueConstraint(
            "session_id",
            "position",
            name="uq_collection_session_position",
        ),
    )

    file_id: Mapped[UUID] = mapped_column(primary_key=True)
    session_id: Mapped[UUID] = mapped_column(
        ForeignKey("collection_sessions.session_id", ondelete="CASCADE"),
        index=True,
    )
    source_message_id: Mapped[int] = mapped_column(BigInteger)
    object_ref: Mapped[str] = mapped_column(String(512))
    byte_size: Mapped[int] = mapped_column(BigInteger)
    position: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


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
            claimed_id = await session.scalar(
                insert(TelegramUpdateRow)
                .values(update_id=update_id)
                .on_conflict_do_nothing(index_elements=[TelegramUpdateRow.update_id])
                .returning(TelegramUpdateRow.update_id)
            )
            await session.commit()
            return claimed_id is not None


class PostgresJobRepository:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        admission_policy: JobAdmissionPolicy | None = None,
    ) -> None:
        self._sessions = sessions
        self._admission_policy = admission_policy or JobAdmissionPolicy()

    async def create_or_get(self, command: CreateJob) -> tuple[JobSnapshot, bool]:
        async with (
            self._sessions() as session,
            session.begin(),
        ):
            existing = await session.scalar(
                select(JobRow).where(JobRow.idempotency_key == command.idempotency_key)
            )
            if existing is not None:
                return _snapshot(existing), False

            await session.execute(select(func.pg_advisory_xact_lock(_GLOBAL_JOB_LOCK)))
            await session.execute(
                select(func.pg_advisory_xact_lock(_user_job_lock(command.user_id)))
            )

            existing = await session.scalar(
                select(JobRow).where(JobRow.idempotency_key == command.idempotency_key)
            )
            if existing is not None:
                return _snapshot(existing), False

            active_values = tuple(state.value for state in ACTIVE_STATES)
            global_active = int(
                await session.scalar(
                    select(func.count())
                    .select_from(JobRow)
                    .where(JobRow.state.in_(active_values))
                )
                or 0
            )
            if global_active >= self._admission_policy.max_active_global:
                raise JobAdmissionRejected(JobAdmissionCode.GLOBAL_CONCURRENCY)

            user_active = int(
                await session.scalar(
                    select(func.count())
                    .select_from(JobRow)
                    .where(
                        JobRow.user_id == command.user_id,
                        JobRow.state.in_(active_values),
                    )
                )
                or 0
            )
            if user_active >= self._admission_policy.max_active_per_user:
                raise JobAdmissionRejected(JobAdmissionCode.USER_CONCURRENCY)

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
            await session.flush()
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


class PostgresCollectionSessionRepository:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        policy: SessionPolicy | None = None,
    ) -> None:
        self._sessions = sessions
        self._policy = policy or SessionPolicy()

    async def create(
        self,
        *,
        kind: SessionKind,
        owner_user_id: int,
        chat_id: int,
        now: datetime | None = None,
    ) -> CollectionSessionSnapshot:
        current = now or utc_now()
        row = CollectionSessionRow(
            session_id=uuid4(),
            kind=kind.value,
            state=SessionState.COLLECTING.value,
            owner_user_id=owner_user_id,
            chat_id=chat_id,
            expires_at=current + self._policy.ttl,
            file_count=0,
            total_bytes=0,
            created_at=current,
            updated_at=current,
        )
        async with self._sessions() as session:
            session.add(row)
            await session.flush()
            snapshot = await _collection_snapshot(session, row)
            await session.commit()
            return snapshot

    async def get_owned(
        self,
        session_id: UUID,
        *,
        owner_user_id: int,
        chat_id: int,
    ) -> CollectionSessionSnapshot:
        async with self._sessions() as session:
            row = await session.get(CollectionSessionRow, session_id)
            if row is None:
                raise SessionNotFound(str(session_id))
            _ensure_session_owner(row, owner_user_id=owner_user_id, chat_id=chat_id)
            return await _collection_snapshot(session, row)

    async def add_file(
        self,
        session_id: UUID,
        *,
        owner_user_id: int,
        chat_id: int,
        item: SessionFileInput,
        now: datetime | None = None,
    ) -> tuple[CollectionSessionSnapshot, bool]:
        current = now or utc_now()
        async with self._sessions() as session:
            row = await _locked_collection_row(session, session_id)
            _ensure_session_owner(row, owner_user_id=owner_user_id, chat_id=chat_id)
            _ensure_collecting(row, current)

            existing = await session.scalar(
                select(CollectionSessionFileRow).where(
                    CollectionSessionFileRow.session_id == session_id,
                    CollectionSessionFileRow.source_message_id == item.source_message_id,
                )
            )
            if existing is not None:
                if existing.object_ref != item.object_ref or existing.byte_size != item.byte_size:
                    raise SessionIdempotencyConflict(
                        "same source_message_id was observed with different file metadata"
                    )
                snapshot = await _collection_snapshot(session, row)
                await session.commit()
                return snapshot, False

            if row.file_count >= self._policy.max_files:
                raise SessionLimitExceeded("session file-count limit exceeded")
            if row.total_bytes + item.byte_size > self._policy.max_aggregate_bytes:
                raise SessionLimitExceeded("session aggregate byte limit exceeded")

            last_position = await session.scalar(
                select(func.max(CollectionSessionFileRow.position)).where(
                    CollectionSessionFileRow.session_id == session_id
                )
            )
            position = int(last_position or 0) + 1
            session.add(
                CollectionSessionFileRow(
                    file_id=uuid4(),
                    session_id=session_id,
                    source_message_id=item.source_message_id,
                    object_ref=item.object_ref,
                    byte_size=item.byte_size,
                    position=position,
                    created_at=current,
                )
            )
            row.file_count += 1
            row.total_bytes += item.byte_size
            row.updated_at = current
            await session.flush()
            snapshot = await _collection_snapshot(session, row)
            await session.commit()
            return snapshot, True

    async def remove_file(
        self,
        session_id: UUID,
        *,
        owner_user_id: int,
        chat_id: int,
        file_id: UUID,
        now: datetime | None = None,
    ) -> CollectionSessionSnapshot:
        current = now or utc_now()
        async with self._sessions() as session:
            row = await _locked_collection_row(session, session_id)
            _ensure_session_owner(row, owner_user_id=owner_user_id, chat_id=chat_id)
            _ensure_collecting(row, current)

            file_row = await session.scalar(
                select(CollectionSessionFileRow).where(
                    CollectionSessionFileRow.session_id == session_id,
                    CollectionSessionFileRow.file_id == file_id,
                )
            )
            if file_row is None:
                raise SessionFileNotFound(str(file_id))

            row.file_count -= 1
            row.total_bytes -= file_row.byte_size
            row.updated_at = current
            await session.delete(file_row)
            await session.flush()
            snapshot = await _collection_snapshot(session, row)
            await session.commit()
            return snapshot

    async def finalize(
        self,
        session_id: UUID,
        *,
        owner_user_id: int,
        chat_id: int,
        now: datetime | None = None,
    ) -> FinalizedSessionPlan:
        current = now or utc_now()
        async with self._sessions() as session:
            row = await _locked_collection_row(session, session_id)
            _ensure_session_owner(row, owner_user_id=owner_user_id, chat_id=chat_id)

            if SessionState(row.state) is SessionState.FINALIZED:
                snapshot = await _collection_snapshot(session, row)
                await session.commit()
                return finalization_plan(snapshot)

            _ensure_collecting(row, current)
            if row.file_count <= 0:
                raise SessionEmpty("cannot finalize an empty collection session")

            row.state = SessionState.FINALIZED.value
            row.updated_at = current
            await session.flush()
            snapshot = await _collection_snapshot(session, row)
            await session.commit()
            return finalization_plan(snapshot)

    async def cancel(
        self,
        session_id: UUID,
        *,
        owner_user_id: int,
        chat_id: int,
    ) -> None:
        async with self._sessions() as session:
            row = await _locked_collection_row(session, session_id)
            _ensure_session_owner(row, owner_user_id=owner_user_id, chat_id=chat_id)
            if SessionState(row.state) is not SessionState.COLLECTING:
                raise SessionClosed("only collecting sessions can be cancelled")
            await session.delete(row)
            await session.commit()

    async def reap_expired(self, *, now: datetime | None = None) -> int:
        current = now or utc_now()
        async with self._sessions() as session:
            result = await session.execute(
                delete(CollectionSessionRow).where(
                    CollectionSessionRow.state == SessionState.COLLECTING.value,
                    CollectionSessionRow.expires_at <= current,
                )
            )
            await session.commit()
            return int(getattr(result, "rowcount", 0) or 0)


async def _locked_collection_row(
    session: AsyncSession,
    session_id: UUID,
) -> CollectionSessionRow:
    row = await session.scalar(
        select(CollectionSessionRow)
        .where(CollectionSessionRow.session_id == session_id)
        .with_for_update()
    )
    if row is None:
        raise SessionNotFound(str(session_id))
    return row


def _ensure_session_owner(
    row: CollectionSessionRow,
    *,
    owner_user_id: int,
    chat_id: int,
) -> None:
    if row.owner_user_id != owner_user_id or row.chat_id != chat_id:
        raise SessionAccessDenied("collection session belongs to another user or chat")


def _ensure_collecting(row: CollectionSessionRow, now: datetime) -> None:
    if SessionState(row.state) is not SessionState.COLLECTING:
        raise SessionClosed("collection session is not accepting changes")
    if now >= row.expires_at:
        raise SessionExpired("collection session has expired")


async def _collection_snapshot(
    session: AsyncSession,
    row: CollectionSessionRow,
) -> CollectionSessionSnapshot:
    file_rows = (
        await session.scalars(
            select(CollectionSessionFileRow)
            .where(CollectionSessionFileRow.session_id == row.session_id)
            .order_by(CollectionSessionFileRow.position)
        )
    ).all()
    files = tuple(
        SessionFileSnapshot(
            file_id=file_row.file_id,
            source_message_id=file_row.source_message_id,
            object_ref=file_row.object_ref,
            byte_size=file_row.byte_size,
            position=file_row.position,
        )
        for file_row in file_rows
    )
    return CollectionSessionSnapshot(
        session_id=row.session_id,
        kind=SessionKind(row.kind),
        state=SessionState(row.state),
        owner_user_id=row.owner_user_id,
        chat_id=row.chat_id,
        expires_at=row.expires_at,
        file_count=row.file_count,
        total_bytes=row.total_bytes,
        files=files,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
