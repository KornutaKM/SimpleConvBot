from simpleconvbot.services import StartJobRequest


def test_session_job_idempotency_is_independent_of_callback_message() -> None:
    first = StartJobRequest(
        user_id=1,
        chat_id=2,
        source_message_id=100,
        operation_id="pdf.merge",
        operation_version=1,
        idempotency_token="8f1b5ee8-4233-4a15-95dc-d4d86338505b",
    )
    repeated = StartJobRequest(
        user_id=1,
        chat_id=2,
        source_message_id=999,
        operation_id="pdf.merge",
        operation_version=1,
        idempotency_token="8f1b5ee8-4233-4a15-95dc-d4d86338505b",
    )

    assert first.idempotency_key == repeated.idempotency_key
    assert first.idempotency_key.startswith("telegram-session:")


def test_single_file_job_idempotency_contract_is_unchanged() -> None:
    request = StartJobRequest(
        user_id=1,
        chat_id=2,
        source_message_id=3,
        operation_id="image.to_png",
        operation_version=1,
    )

    assert request.idempotency_key == "telegram:2:1:3:image.to_png:v1"
