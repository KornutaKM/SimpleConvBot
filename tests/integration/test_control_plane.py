from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
from pathlib import Path
from uuid import UUID

import pytest
from redis.asyncio import Redis

from simpleconvbot.jobs import CreateJob, JobState
from simpleconvbot.metrics import MetricsRegistry
from simpleconvbot.operations import OperationDefinition, OperationRegistry
from simpleconvbot.ports import ExecutionResult
from simpleconvbot.postgres import (
    PostgresJobRepository,
    PostgresUpdateReceiptStore,
    create_schema,
    drop_schema,
    make_engine,
    make_session_factory,
)
from simpleconvbot.redis_queue import RedisJobQueue
from simpleconvbot.services import JobService, JobWorker, QueueWorker, StartJobRequest
from simpleconvbot.storage import LocalTemporaryStorage
from simpleconvbot.telemetry import OperationStage


class CountingExecutor:
    def __init__(self) -> None:
        self.calls = 0

    async def execute(
        self,
        job: object,
        operation: object,
        workspace: Path,
    ) -> ExecutionResult:
        del job, operation
        self.calls += 1
        output = workspace / "noop.txt"
        output.write_text("noop", encoding="utf-8")
        return ExecutionResult(output_ref=str(output))


class FailingQueue:
    async def enqueue(self, job_id: UUID) -> None:
        del job_id
        raise RuntimeError("synthetic queue uncertainty")

    async def reserve(self, timeout_seconds: int) -> UUID | None:
        del timeout_seconds
        return None

    async def ack(self, job_id: UUID) -> None:
        del job_id

    async def recover_inflight(self) -> int:
        return 0


class FailingExecutor:
    async def execute(
        self,
        job: object,
        operation: object,
        workspace: Path,
    ) -> ExecutionResult:
        del job, operation
        (workspace / "partial.bin").write_bytes(b"partial")
        raise RuntimeError("synthetic conversion failure")


class RecordingDelivery:
    def __init__(self) -> None:
        self.outputs: list[str] = []

    async def deliver(self, job: object, result: ExecutionResult) -> None:
        del job
        self.outputs.append(result.output_ref)


class RecordingFailureDelivery:
    def __init__(self) -> None:
        self.error_codes: list[str] = []

    async def deliver_failure(self, job: object, error_code: str) -> None:
        del job
        self.error_codes.append(error_code)


@pytest.mark.integration
def test_duplicate_update_and_callback_execute_once() -> None:
    asyncio.run(_duplicate_update_and_callback_execute_once())


async def _duplicate_update_and_callback_execute_once() -> None:
    database_url = os.environ["DATABASE_URL"]
    redis_url = os.environ["REDIS_URL"]
    engine = make_engine(database_url)
    sessions = make_session_factory(engine)
    redis_client = Redis.from_url(redis_url, decode_responses=True)
    temp_root = Path(tempfile.mkdtemp(prefix="simpleconvbot-test-"))

    try:
        await drop_schema(engine)
        await create_schema(engine)
        await redis_client.flushdb()

        receipts = PostgresUpdateReceiptStore(sessions)
        assert await receipts.claim(1001)
        assert not await receipts.claim(1001)

        repository = PostgresJobRepository(sessions)
        queue = RedisJobQueue(redis_client, prefix="test:jobs")
        registry = OperationRegistry([OperationDefinition("test.noop", 1, "test")])
        metrics = MetricsRegistry()
        service = JobService(repository, queue, registry, metrics=metrics)
        request = StartJobRequest(
            user_id=10,
            chat_id=20,
            source_message_id=30,
            operation_id="test.noop",
            operation_version=1,
        )

        first = await service.start_operation(request)
        second = await service.start_operation(request)

        assert first.created
        assert not second.created
        assert first.job.job_id == second.job.job_id
        assert second.job.state is JobState.QUEUED

        executor = CountingExecutor()
        delivery = RecordingDelivery()
        worker = JobWorker(
            repository=repository,
            registry=registry,
            storage=LocalTemporaryStorage(temp_root),
            executor=executor,
            delivery=delivery,
            metrics=metrics,
        )
        runner = QueueWorker(queue, worker)

        assert await runner.run_once()
        assert await runner.run_once()

        final = await repository.get(first.job.job_id)
        assert final.state is JobState.COMPLETED
        assert executor.calls == 1
        assert len(delivery.outputs) == 1

        snapshot = metrics.snapshot()
        queue_metrics = [
            item
            for item in snapshot.operations
            if item.operation_id == "test.noop" and item.stage is OperationStage.QUEUE
        ]
        cleanup_metrics = [
            item
            for item in snapshot.operations
            if item.operation_id == "test.noop" and item.stage is OperationStage.CLEANUP
        ]
        assert queue_metrics
        assert queue_metrics[0].succeeded >= 1
        assert cleanup_metrics
        assert cleanup_metrics[0].succeeded == 1
    finally:
        await redis_client.aclose()
        await engine.dispose()
        shutil.rmtree(temp_root, ignore_errors=True)


@pytest.mark.integration
def test_failed_execution_cleans_workspace_and_marks_job_failed() -> None:
    asyncio.run(_failed_execution_cleans_workspace_and_marks_job_failed())


async def _failed_execution_cleans_workspace_and_marks_job_failed() -> None:
    database_url = os.environ["DATABASE_URL"]
    redis_url = os.environ["REDIS_URL"]
    engine = make_engine(database_url)
    sessions = make_session_factory(engine)
    redis_client = Redis.from_url(redis_url, decode_responses=True)
    temp_root = Path(tempfile.mkdtemp(prefix="simpleconvbot-failure-test-"))

    try:
        await drop_schema(engine)
        await create_schema(engine)
        await redis_client.flushdb()

        repository = PostgresJobRepository(sessions)
        queue = RedisJobQueue(redis_client, prefix="test:failure")
        registry = OperationRegistry([OperationDefinition("test.noop", 1, "test")])
        service = JobService(repository, queue, registry)
        started = await service.start_operation(
            StartJobRequest(
                user_id=101,
                chat_id=202,
                source_message_id=303,
                operation_id="test.noop",
                operation_version=1,
            )
        )

        failure_delivery = RecordingFailureDelivery()
        worker = JobWorker(
            repository=repository,
            registry=registry,
            storage=LocalTemporaryStorage(temp_root),
            executor=FailingExecutor(),
            delivery=RecordingDelivery(),
            failure_delivery=failure_delivery,
        )
        runner = QueueWorker(queue, worker)

        assert await runner.run_once()

        final = await repository.get(started.job.job_id)
        assert final.state is JobState.FAILED
        assert not (temp_root / str(started.job.job_id)).exists()
        assert failure_delivery.error_codes == ["internal_error"]
    finally:
        await redis_client.aclose()
        await engine.dispose()
        shutil.rmtree(temp_root, ignore_errors=True)


@pytest.mark.integration
def test_queue_submission_uncertainty_fails_job_closed() -> None:
    asyncio.run(_queue_submission_uncertainty_fails_job_closed())


async def _queue_submission_uncertainty_fails_job_closed() -> None:
    database_url = os.environ["DATABASE_URL"]
    engine = make_engine(database_url)
    sessions = make_session_factory(engine)

    try:
        await drop_schema(engine)
        await create_schema(engine)

        repository = PostgresJobRepository(sessions)
        service = JobService(
            repository,
            FailingQueue(),
            OperationRegistry([OperationDefinition("test.noop", 1, "test")]),
        )
        request = StartJobRequest(
            user_id=71,
            chat_id=72,
            source_message_id=73,
            operation_id="test.noop",
            operation_version=1,
        )

        with pytest.raises(RuntimeError, match="queue uncertainty"):
            await service.start_operation(request)

        job, created = await repository.create_or_get(
            CreateJob(
                idempotency_key=request.idempotency_key,
                operation_id=request.operation_id,
                operation_version=request.operation_version,
                user_id=request.user_id,
                chat_id=request.chat_id,
                source_message_id=request.source_message_id,
            )
        )
        assert not created
        assert job.state is JobState.FAILED
    finally:
        await engine.dispose()


@pytest.mark.integration
def test_repository_restart_preserves_uncertain_state() -> None:
    asyncio.run(_repository_restart_preserves_uncertain_state())


async def _repository_restart_preserves_uncertain_state() -> None:
    database_url = os.environ["DATABASE_URL"]
    redis_url = os.environ["REDIS_URL"]
    engine = make_engine(database_url)
    sessions = make_session_factory(engine)
    redis_client = Redis.from_url(redis_url, decode_responses=True)

    try:
        await drop_schema(engine)
        await create_schema(engine)
        await redis_client.flushdb()

        repository = PostgresJobRepository(sessions)
        queue = RedisJobQueue(redis_client, prefix="test:restart")
        registry = OperationRegistry([OperationDefinition("test.noop", 1, "test")])
        service = JobService(repository, queue, registry)

        started = await service.start_operation(
            StartJobRequest(
                user_id=1,
                chat_id=2,
                source_message_id=3,
                operation_id="test.noop",
                operation_version=1,
            )
        )
        processing = await repository.transition(
            started.job.job_id,
            JobState.QUEUED,
            JobState.PROCESSING,
        )
        assert processing.state is JobState.PROCESSING

        repository_after_restart = PostgresJobRepository(make_session_factory(engine))
        recovered = await repository_after_restart.get(UUID(str(started.job.job_id)))

        assert recovered.state is JobState.PROCESSING
    finally:
        await redis_client.aclose()
        await engine.dispose()
