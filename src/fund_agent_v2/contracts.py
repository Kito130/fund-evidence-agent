from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class ToolPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    arbitrary_shell_allowed: Literal[False]
    arbitrary_filesystem_allowed: Literal[False]
    allowlist_required: Literal[True]
    strict_schemas_required: Literal[True]


class FundAgentPhase1Config(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    project_id: Literal["fund_agent"]
    phase: Literal["PHASE_1"]
    random_seed: int
    data_registry_path: str
    execution_enabled: Literal[False]
    llm_enabled: Literal[False]
    network_enabled: Literal[False]
    paid_api_enabled: Literal[False]
    export_enabled: Literal[False]
    data_write_policy: Literal["V2_OUTPUTS_ONLY"]
    api_gate_status: Literal["PENDING_OFFICIAL_DOCS_VERIFICATION"]
    agent_architecture: Literal["SINGLE_AGENT_BASELINE_FIRST"]
    old_holdout_policy: Literal["FROZEN_DO_NOT_READ"]
    tool_policy: ToolPolicy
    retrieval_sequence: list[str]
    output_root: str
