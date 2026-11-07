"""Local IPC server (ACE_MASTER_PLAN.md §5.5, §15.1).

FastAPI + Uvicorn bound to 127.0.0.1 only (random port by default).
- WebSocket ``/ws``: the first message must carry the per-run token within 2 s; browsers may only
  connect from ACE's own origins; frames are capped at 1 MiB and rate-limited per connection; at
  most 8 clients. Every outbound frame goes through one writer task per connection.
- REST ``GET /api/v1/health`` with ``Authorization: Bearer <token>``.
- A Host-header allowlist (127.0.0.1 only) blocks DNS-rebinding tricks from web pages.
"""

from __future__ import annotations

import asyncio
import contextlib
import socket
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Final

import structlog
import uvicorn
from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.middleware.trustedhost import TrustedHostMiddleware

from ace_core.app.container import Container
from ace_core.app.events import Event
from ace_core.app.version import __version__
from ace_core.ipc import protocol
from ace_core.ipc.events import to_ipc_event
from ace_core.ipc.methods import METHODS, MethodContext, core_state_info, health_result
from ace_core.ipc.protocol import ProtocolError, validation_summary
from ace_core.ipc.schemas import (
    MAX_MESSAGE_BYTES,
    PROTOCOL_VERSION,
    AuthMessage,
    ErrorCode,
    RequestMessage,
    SessionReadyPayload,
)
from ace_core.ipc.security import (
    MIN_TOKEN_LENGTH,
    TokenBucket,
    new_token,
    origin_allowed,
    tokens_match,
)

log = structlog.stdlib.get_logger(__name__)

LOOPBACK: Final = "127.0.0.1"
CLOSE_GOING_AWAY: Final = 1001
CLOSE_POLICY_VIOLATION: Final = 1008
CLOSE_TRY_AGAIN_LATER: Final = 1013
CLOSE_UNAUTHORIZED: Final = 4401
_SEND_TIMEOUT_S: Final = 5.0
_FLUSH_TIMEOUT_S: Final = 0.5  # on stop: time for queued frames (e.g. system.stopping) to go out


@dataclass(frozen=True, slots=True)
class IpcLimits:
    auth_timeout_s: float = 2.0
    max_clients: int = 8
    outbox_size: int = 256
    rate_per_s: float = 30.0
    rate_burst: int = 60


class _ServerWithoutSignals(uvicorn.Server):
    """Uvicorn would install its own Ctrl+C handlers; the App lifecycle owns them (S01)."""

    @contextlib.contextmanager
    def capture_signals(self) -> Iterator[None]:
        yield


@dataclass(eq=False)
class _Client:
    websocket: WebSocket
    outbox: asyncio.Queue[str]
    dropped: int = 0

    async def send(self, text: str) -> None:
        """Queue a frame that must arrive (responses). Raises TimeoutError for a stuck client."""
        await asyncio.wait_for(self.outbox.put(text), timeout=_SEND_TIMEOUT_S)

    def offer(self, text: str) -> None:
        """Queue a frame that may be dropped when the client is too slow (events)."""
        try:
            self.outbox.put_nowait(text)
        except asyncio.QueueFull:
            self.dropped += 1


class IpcServer:
    def __init__(
        self,
        container: Container,
        *,
        port: int = 0,
        token: str | None = None,
        limits: IpcLimits | None = None,
    ) -> None:
        self._container = container
        self._requested_port = port
        self._token = token if token is not None else new_token()
        self._limits = limits if limits is not None else IpcLimits()
        self._dev = container.settings.dev
        self._clients: set[_Client] = set()
        self._socket: socket.socket | None = None
        self._server: _ServerWithoutSignals | None = None
        self._serve_task: asyncio.Task[None] | None = None
        self._unsubscribe: Callable[[], None] | None = None
        self.port = 0
        self.app = self._build_app()

    @property
    def token(self) -> str:
        return self._token

    @property
    def client_count(self) -> int:
        return len(self._clients)

    def _build_app(self) -> FastAPI:
        app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=[LOOPBACK])
        app.add_api_websocket_route("/ws", self._ws_endpoint)
        app.add_api_route("/api/v1/health", self._rest_health, methods=["GET"], response_model=None)
        return app

    # ---- lifecycle ----

    async def start(self) -> int:
        if len(self._token) < MIN_TOKEN_LENGTH:
            raise ValueError(f"IPC token must be at least {MIN_TOKEN_LENGTH} characters long")
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):  # Windows: no other process may share the port
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        sock.bind((LOOPBACK, self._requested_port))
        sock.listen()
        self._socket = sock
        self.port = int(sock.getsockname()[1])

        config = uvicorn.Config(
            self.app,
            log_config=None,
            access_log=False,
            server_header=False,
            proxy_headers=False,
            lifespan="off",
            ws="websockets-sansio",
            ws_max_size=MAX_MESSAGE_BYTES,
            limit_concurrency=64,
            timeout_graceful_shutdown=2,
        )
        server = _ServerWithoutSignals(config)
        self._server = server
        self._unsubscribe = self._container.bus.subscribe(Event, self._on_bus_event)
        task = asyncio.get_running_loop().create_task(server.serve(sockets=[sock]), name="ace-ipc")
        self._serve_task = task
        for _ in range(500):
            if server.started:
                log.info("ipc listening", host=LOOPBACK, port=self.port, dev=self._dev)
                return self.port
            if task.done():
                break
            await asyncio.sleep(0.01)
        await self.stop()
        raise RuntimeError("the IPC server did not start")

    async def stop(self) -> None:
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None
        clients = list(self._clients)
        if clients:
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(
                    asyncio.gather(*(client.outbox.join() for client in clients)),
                    timeout=_FLUSH_TIMEOUT_S,
                )
        for client in clients:
            with contextlib.suppress(Exception):
                await client.websocket.close(code=CLOSE_GOING_AWAY, reason="ace-core is stopping")
        if self._server is not None:
            self._server.should_exit = True
        if self._serve_task is not None:
            with contextlib.suppress(Exception):
                await asyncio.wait_for(self._serve_task, timeout=5.0)
            self._serve_task = None
        if self._socket is not None:
            self._socket.close()
            self._socket = None

    # ---- events: bus -> every connected client ----

    async def _on_bus_event(self, event: Event) -> None:
        mapped = to_ipc_event(event)
        if mapped is None:
            return
        name, payload = mapped
        frame = protocol.event(name, payload)
        for client in list(self._clients):
            client.offer(frame)

    # ---- REST ----

    async def _rest_health(self, request: Request) -> JSONResponse:
        if not origin_allowed(request.headers.get("origin"), dev=self._dev):
            return JSONResponse({"error": "origin not allowed"}, status_code=403)
        scheme, _, provided = request.headers.get("authorization", "").partition(" ")
        if scheme.lower() != "bearer" or not provided or not tokens_match(self._token, provided):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        return JSONResponse(health_result(self._container).model_dump(mode="json"))

    # ---- WebSocket ----

    async def _ws_endpoint(self, websocket: WebSocket) -> None:
        origin = websocket.headers.get("origin")
        if not origin_allowed(origin, dev=self._dev):
            log.warning("ipc connection refused: origin not allowed", origin=origin)
            await websocket.close(code=CLOSE_POLICY_VIOLATION)  # before accept -> HTTP 403
            return
        if len(self._clients) >= self._limits.max_clients:
            log.warning("ipc connection refused: too many clients")
            await websocket.close(code=CLOSE_TRY_AGAIN_LATER)
            return
        await websocket.accept()
        if not await self._authenticate(websocket):
            return

        client = _Client(websocket, asyncio.Queue(self._limits.outbox_size))
        ready = SessionReadyPayload(
            version=__version__,
            protocol=PROTOCOL_VERSION,
            dev=self._dev,
            state=core_state_info(self._container.state.current),
        )
        # Queue session.ready BEFORE joining the event fan-out, so it is always the first frame.
        client.offer(protocol.event("session.ready", ready))
        self._clients.add(client)
        writer = asyncio.get_running_loop().create_task(self._write_loop(client))
        try:
            await self._read_loop(client)
        except (TimeoutError, ConnectionError):
            log.warning("ipc client stopped reading; disconnecting")
        finally:
            self._clients.discard(client)
            writer.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await writer
            if client.dropped:
                log.warning("ipc client missed events", dropped=client.dropped)

    async def _authenticate(self, websocket: WebSocket) -> bool:
        try:
            message = await asyncio.wait_for(websocket.receive(), self._limits.auth_timeout_s)
        except TimeoutError:
            await websocket.close(code=CLOSE_UNAUTHORIZED, reason="authentication timed out")
            return False
        if message["type"] == "websocket.disconnect":
            return False
        try:
            parsed = protocol.parse_incoming(message.get("text") or "")
        except ProtocolError:
            parsed = None
        if not isinstance(parsed, AuthMessage) or not tokens_match(self._token, parsed.token):
            log.warning("ipc connection refused: missing or wrong token")
            await websocket.close(code=CLOSE_UNAUTHORIZED, reason="unauthorized")
            return False
        return True

    async def _write_loop(self, client: _Client) -> None:
        with contextlib.suppress(Exception):  # a disconnect ends the writer
            while True:
                frame = await client.outbox.get()
                await client.websocket.send_text(frame)
                client.outbox.task_done()  # lets stop() wait for queued frames

    async def _read_loop(self, client: _Client) -> None:
        bucket = TokenBucket(self._limits.rate_per_s, self._limits.rate_burst)
        while True:
            message = await client.websocket.receive()
            if message["type"] == "websocket.disconnect":
                return
            text = message.get("text")
            if text is None:
                await client.send(
                    protocol.error(ErrorCode.BAD_MESSAGE, "binary frames are not supported")
                )
                continue
            if not bucket.allow():
                await client.send(protocol.error(ErrorCode.RATE_LIMITED, "too many messages"))
                continue
            try:
                incoming = protocol.parse_incoming(text)
            except ProtocolError as exc:
                await client.send(protocol.error_from(exc))
                continue
            if isinstance(incoming, AuthMessage):
                await client.send(protocol.error(ErrorCode.BAD_MESSAGE, "already authenticated"))
                continue
            await client.send(await self._dispatch(incoming))

    async def _dispatch(self, request: RequestMessage) -> str:
        spec = METHODS.get(request.method)
        if spec is None:
            return protocol.error(
                ErrorCode.UNKNOWN_METHOD,
                f"unknown method: {request.method}",
                request_id=request.id,
                method=request.method,
            )
        if spec.dev_only and not self._dev:
            return protocol.error(
                ErrorCode.DEV_ONLY,
                f"{request.method} is only available in dev mode",
                request_id=request.id,
                method=request.method,
            )
        try:
            params = spec.params.model_validate(request.params)
            result = await spec.handler(MethodContext(self._container), params)
        except ValidationError as exc:
            return protocol.error(
                ErrorCode.BAD_PARAMS,
                "invalid params",
                request_id=request.id,
                method=request.method,
                details=validation_summary(exc),
            )
        except Exception:
            log.exception("ipc method failed", method=request.method)
            return protocol.error(
                ErrorCode.INTERNAL,
                "internal error",
                request_id=request.id,
                method=request.method,
            )
        return protocol.response(request, result)
