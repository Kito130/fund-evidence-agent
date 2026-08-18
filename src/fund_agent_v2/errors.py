from __future__ import annotations

from enum import StrEnum


class ToolErrorCode(StrEnum):
    INVALID_INPUT = "INVALID_INPUT"
    POLICY_VIOLATION = "POLICY_VIOLATION"
    NOT_FOUND = "NOT_FOUND"
    DATA_INTEGRITY = "DATA_INTEGRITY"
    TIMEOUT = "TIMEOUT"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class ToolError(Exception):
    def __init__(
        self,
        code: ToolErrorCode,
        message: str,
        *,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class ToolTimeoutError(ToolError):
    def __init__(self, tool_name: str, timeout_seconds: float) -> None:
        super().__init__(
            ToolErrorCode.TIMEOUT,
            f"{tool_name} exceeded {timeout_seconds:.3f}s timeout",
            retryable=True,
        )
