"""テスト生成物をプロジェクト内へ保存し、制限されたOS一時領域を使わない。"""

import uuid
from pathlib import Path

import pytest


@pytest.fixture
def workspace_path():
    path = (
        Path(__file__).resolve().parents[1]
        / "artifacts"
        / "test-temp"
        / uuid.uuid4().hex
    )
    path.mkdir(parents=True)
    return path
