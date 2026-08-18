from __future__ import annotations

import json
from pathlib import Path

import yaml

from .phase7_schemas import EvalCase, FundAgentPhase7Config
from .tools import WORKSPACE_ROOT

DEFAULT_PHASE7_CONFIG = WORKSPACE_ROOT / "configs/phase7_agent.yaml"
EVAL_ROOT = (WORKSPACE_ROOT / "eval/v2").resolve()


def load_phase7_config(path: Path = DEFAULT_PHASE7_CONFIG) -> FundAgentPhase7Config:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return FundAgentPhase7Config.model_validate(raw)


def configured_eval_paths(
    config: FundAgentPhase7Config,
) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    for suite, relative in config.evaluation_sets.items():
        path = (WORKSPACE_ROOT / relative).resolve()
        if not path.is_relative_to(EVAL_ROOT):
            raise ValueError(f"evaluation path escaped V2 eval root: {suite}")
        paths[suite] = path
    return paths


def load_eval_cases(config: FundAgentPhase7Config) -> list[EvalCase]:
    cases: list[EvalCase] = []
    seen_ids: set[str] = set()
    for suite, path in configured_eval_paths(config).items():
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if not line.strip():
                continue
            value = json.loads(line)
            case = EvalCase.model_validate(value)
            if case.suite != suite:
                raise ValueError(f"suite mismatch: {path}:{line_number}")
            if case.case_id in seen_ids:
                raise ValueError(f"duplicate case_id: {case.case_id}")
            seen_ids.add(case.case_id)
            cases.append(case)
    return cases
