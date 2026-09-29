from uuid import UUID, uuid4

from simpleconvbot.telegram_sessions import parse_session_callback


def test_session_callback_parser_is_closed_and_uuid_bound() -> None:
    session_id = uuid4()

    assert parse_session_callback(f"sess:add:{session_id}") == ("add", session_id)
    assert parse_session_callback(f"sess:done:{session_id}") == ("done", session_id)
    assert parse_session_callback(f"sess:cancel:{session_id}") == ("cancel", session_id)


def test_session_callback_parser_rejects_free_form_values() -> None:
    assert parse_session_callback(None) is None
    assert parse_session_callback("sess:done:not-a-uuid") is None
    assert parse_session_callback(f"sess:delete:{UUID(int=0)}") is None
    assert parse_session_callback("ui:pdf:merge") is None
