from __future__ import annotations

import pytest

from fund_agent_v2.tools import FundToolbox, build_toolbox


@pytest.fixture
def toolbox() -> FundToolbox:
    return build_toolbox()
