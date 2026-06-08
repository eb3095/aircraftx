from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _redirect_aircraftx_logs(tmp_path, monkeypatch):
    monkeypatch.setenv("AIRCRAFTX_LOG_DIR", str(tmp_path / "logs"))
