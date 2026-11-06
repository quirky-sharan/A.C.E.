"""Protocol: valid parsing, strict rejection, no input echo, fuzzing, outgoing builders."""

import contextlib
import json
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import BaseModel, TypeAdapter

from ace_core.ipc import protocol
from ace_core.ipc.protocol import ProtocolError, parse_incoming
from ace_core.ipc.schemas import (
    AuthMessage,
    ErrorCode,
    OutgoingMessage,
    RequestMessage,
    SystemStoppingPayload,
)

OUTGOING: TypeAdapter[Any] = TypeAdapter(OutgoingMessage)

json_values = st.recursive(
    st.none() | st.booleans() | st.integers() | st.floats(allow_nan=False) | st.text(),
    lambda children: st.lists(children, max_size=5) | st.dictionaries(st.text(), children),
    max_leaves=20,
)


def test_parses_auth_and_request_messages() -> None:
    auth = parse_incoming('{"v": 1, "type": "auth", "token": "abc"}')
    assert isinstance(auth, AuthMessage)
    request = parse_incoming(
        '{"type": "request", "id": "7", "method": "settings.get", "params": {"key": "theme"}}'
    )
    assert isinstance(request, RequestMessage)
    assert request.params == {"key": "theme"}


@pytest.mark.parametrize(
    "raw",
    [
        "not json",
        "[]",
        "42",
        '{"type": "auth"}',
        '{"type": "auth", "token": "x", "extra": 1}',
        '{"type": "hello"}',
        '{"v": 2, "type": "auth", "token": "x"}',
        '{"type": "request", "id": "1", "method": "Bad Method"}',
        '{"type": "request", "id": "1", "method": "nodots"}',
        '{"type": "request", "id": "' + "x" * 65 + '", "method": "system.health"}',
        '{"type": "request", "id": "1", "method": "system.health", "params": []}',
    ],
)
def test_invalid_messages_are_rejected(raw: str) -> None:
    with pytest.raises(ProtocolError) as excinfo:
        parse_incoming(raw)
    assert excinfo.value.code is ErrorCode.BAD_MESSAGE


def test_readable_id_and_method_are_echoed_back() -> None:
    with pytest.raises(ProtocolError) as excinfo:
        parse_incoming('{"type": "request", "id": "abc", "method": "settings.get", "x": 1}')
    assert excinfo.value.request_id == "abc"
    assert excinfo.value.method == "settings.get"


def test_errors_never_echo_the_rejected_input() -> None:
    secret = "gsk_" + "s" * 40  # pragma: allowlist secret
    with pytest.raises(ProtocolError) as excinfo:
        parse_incoming(json.dumps({"type": "auth", "token": 12345, "stray": secret}))
    assert secret not in json.dumps(excinfo.value.details)


@given(st.text(max_size=2000))
def test_any_text_parses_or_raises_protocol_error(text: str) -> None:
    with contextlib.suppress(ProtocolError):
        parse_incoming(text)


@given(json_values)
def test_any_json_value_parses_or_raises_protocol_error(value: object) -> None:
    with contextlib.suppress(ProtocolError):
        parse_incoming(json.dumps(value))


@given(
    st.dictionaries(st.sampled_from(["v", "type", "id", "method", "params", "token"]), json_values)
)
def test_message_shaped_json_parses_or_raises_protocol_error(value: dict[str, object]) -> None:
    with contextlib.suppress(ProtocolError):
        parse_incoming(json.dumps(value))


class _Result(BaseModel):
    ok: bool


def test_outgoing_builders_produce_valid_messages() -> None:
    request = RequestMessage(type="request", id="9", method="system.health")
    frames = [
        protocol.response(request, _Result(ok=True)),
        protocol.error(ErrorCode.UNKNOWN_METHOD, "nope", request_id="9", method="x.y"),
        protocol.event("system.stopping", SystemStoppingPayload(reason="test")),
    ]
    kinds = [OUTGOING.validate_json(frame).type for frame in frames]
    assert kinds == ["response", "error", "event"]
