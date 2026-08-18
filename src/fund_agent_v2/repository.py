from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

from .errors import ToolError, ToolErrorCode
from .policy import ToolPolicy
from .schemas import FundAgentPhase6Config


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_phase6_config(path: Path) -> FundAgentPhase6Config:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return FundAgentPhase6Config.model_validate(raw)


class DatasetRepository:
    def __init__(self, policy: ToolPolicy) -> None:
        self.policy = policy

    def _registered_path(self, logical_name: str) -> Path:
        if logical_name not in self.policy.config.allowed_data_files:
            raise ToolError(
                ToolErrorCode.POLICY_VIOLATION,
                f"data file is not registered: {logical_name}",
            )
        path = (self.policy.dataset_root / logical_name).resolve()
        if not path.is_relative_to(self.policy.dataset_root):
            raise ToolError(ToolErrorCode.POLICY_VIOLATION, "data path escaped root")
        if not path.is_file():
            raise ToolError(
                ToolErrorCode.NOT_FOUND, f"registered file missing: {logical_name}"
            )
        expected = self.policy.config.file_sha256.get(logical_name)
        actual = sha256_file(path)
        if expected is None or actual != expected:
            raise ToolError(
                ToolErrorCode.DATA_INTEGRITY,
                f"registered file hash mismatch: {logical_name}",
            )
        return path

    def json_object(self, logical_name: str) -> dict[str, Any]:
        value = json.loads(
            self._registered_path(logical_name).read_text(encoding="utf-8")
        )
        if not isinstance(value, dict):
            raise ToolError(ToolErrorCode.DATA_INTEGRITY, "JSON root must be object")
        return value

    def jsonl_objects(self, logical_name: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for line in (
            self._registered_path(logical_name).read_text(encoding="utf-8").splitlines()
        ):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ToolError(
                    ToolErrorCode.DATA_INTEGRITY, "JSONL row must be object"
                )
            rows.append(value)
        return rows

    def csv_rows(self, logical_name: str) -> list[dict[str, str]]:
        with self._registered_path(logical_name).open(
            "r", encoding="utf-8", newline=""
        ) as handle:
            return [dict(row) for row in csv.DictReader(handle)]

    def verify_all_registered_hashes(self) -> dict[str, bool]:
        return {
            logical_name: bool(self._registered_path(logical_name))
            for logical_name in self.policy.config.allowed_data_files
        }
