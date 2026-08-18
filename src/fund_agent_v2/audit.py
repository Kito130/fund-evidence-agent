from __future__ import annotations

import hashlib
import threading
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from datetime import UTC, datetime
from typing import TypeVar

from pydantic import BaseModel

from .errors import ToolError, ToolErrorCode, ToolTimeoutError
from .schemas import AuditEvent

OutputT = TypeVar("OutputT", bound=BaseModel)


def _model_hash(model: BaseModel) -> str:
    payload = model.model_dump_json(exclude_none=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class AuditSink:
    def __init__(self) -> None:
        self._events: list[AuditEvent] = []
        self._lock = threading.Lock()

    def append(self, event: AuditEvent) -> None:
        with self._lock:
            self._events.append(event)

    def events(self) -> tuple[AuditEvent, ...]:
        with self._lock:
            return tuple(self._events)


class ToolRuntime:
    def __init__(
        self,
        *,
        allowed_tools: set[str],
        timeouts_seconds: dict[str, float],
        audit_sink: AuditSink,
    ) -> None:
        self._allowed_tools = frozenset(allowed_tools)
        self._timeouts_seconds = dict(timeouts_seconds)
        self._audit_sink = audit_sink

    def invoke(
        self,
        *,
        request_id: str,
        tool_name: str,
        tool_input: BaseModel,
        handler: Callable[[], OutputT],
    ) -> OutputT:
        started_at = datetime.now(UTC)
        input_sha256 = _model_hash(tool_input)
        output: OutputT | None = None
        error: ToolError | None = None

        if tool_name not in self._allowed_tools:
            error = ToolError(
                ToolErrorCode.POLICY_VIOLATION,
                f"tool is not allowlisted: {tool_name}",
            )
        elif tool_name not in self._timeouts_seconds:
            error = ToolError(
                ToolErrorCode.POLICY_VIOLATION,
                f"tool has no registered timeout: {tool_name}",
            )
        else:
            timeout = self._timeouts_seconds[tool_name]
            executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="fund-tool")
            future = executor.submit(handler)
            try:
                output = future.result(timeout=timeout)
            except FutureTimeoutError:
                future.cancel()
                error = ToolTimeoutError(tool_name, timeout)
                executor.shutdown(wait=False, cancel_futures=True)
            except ToolError as exc:
                error = exc
                executor.shutdown(wait=True)
            except Exception as exc:  # noqa: BLE001  # pragma: no cover
                error = ToolError(
                    ToolErrorCode.INTERNAL_ERROR,
                    f"unexpected {type(exc).__name__}",
                )
                executor.shutdown(wait=True)
            else:
                executor.shutdown(wait=True)

        finished_at = datetime.now(UTC)
        duration_ms = (finished_at - started_at).total_seconds() * 1000.0
        event = AuditEvent(
            event_id=uuid.uuid4().hex,
            request_id=request_id,
            tool_name=tool_name,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
            status="ERROR" if error else "SUCCESS",
            input_sha256=input_sha256,
            output_sha256=_model_hash(output) if output is not None else None,
            error_code=error.code.value if error else None,
            retryable=error.retryable if error else False,
        )
        self._audit_sink.append(event)
        if error is not None:
            raise error
        if output is None:  # pragma: no cover - impossible after successful handler
            raise RuntimeError("tool returned no output")
        return output
