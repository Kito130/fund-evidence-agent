from __future__ import annotations

from pathlib import Path
from urllib.parse import urlsplit

from .errors import ToolError, ToolErrorCode
from .schemas import FundAgentPhase6Config


class ToolPolicy:
    def __init__(self, *, config: FundAgentPhase6Config, workspace_root: Path) -> None:
        self.config = config
        self.workspace_root = workspace_root.resolve()
        self.dataset_root = (self.workspace_root / config.dataset_root).resolve()
        self.export_root = (self.workspace_root / config.export_root).resolve()
        self._ensure_within(self.dataset_root, self.workspace_root, "dataset root")
        self._ensure_within(self.export_root, self.workspace_root, "export root")

    @staticmethod
    def _ensure_within(path: Path, parent: Path, label: str) -> None:
        if not path.is_relative_to(parent):
            raise ToolError(
                ToolErrorCode.POLICY_VIOLATION,
                f"{label} is outside the workspace allowlist",
            )

    def require_funds(self, fund_codes: list[str]) -> None:
        unknown = sorted(set(fund_codes) - set(self.config.allowed_fund_codes))
        if unknown:
            raise ToolError(
                ToolErrorCode.POLICY_VIOLATION,
                f"fund code is outside the allowlist: {', '.join(unknown)}",
            )
        if len(fund_codes) != len(set(fund_codes)):
            raise ToolError(ToolErrorCode.INVALID_INPUT, "fund codes must be unique")

    def require_periods(self, periods: list[str]) -> None:
        unknown = sorted(set(periods) - set(self.config.allowed_periods))
        if unknown:
            raise ToolError(
                ToolErrorCode.POLICY_VIOLATION,
                f"period is outside the allowlist: {', '.join(unknown)}",
            )
        if len(periods) != len(set(periods)):
            raise ToolError(ToolErrorCode.INVALID_INPUT, "periods must be unique")

    def require_official_url(self, url: str) -> str:
        parsed = urlsplit(url)
        domain = (parsed.hostname or "").lower()
        if (
            parsed.scheme != "https"
            or domain not in self.config.allowed_official_domains
        ):
            raise ToolError(
                ToolErrorCode.POLICY_VIOLATION,
                "URL is not an allowlisted HTTPS official source",
            )
        if parsed.username or parsed.password or parsed.port not in (None, 443):
            raise ToolError(
                ToolErrorCode.POLICY_VIOLATION, "URL authority is not allowed"
            )
        return domain

    def export_path(self, file_name: str) -> Path:
        candidate = (self.export_root / file_name).resolve()
        self._ensure_within(candidate, self.export_root, "export path")
        return candidate
