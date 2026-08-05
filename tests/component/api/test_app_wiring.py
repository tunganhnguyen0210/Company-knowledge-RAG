from pathlib import Path
from typing import cast

import pytest

from api.app import create_app
from providers.base import GenerationProvider
from retrieval.memory_store import MemoryChunkStore
from settings import Settings

pytestmark = pytest.mark.component


def test_create_app_shares_tracer_between_ingestion_and_chat(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,
        registry_path=tmp_path / "registry.json",
        upload_dir=tmp_path / "uploads",
    )

    app = create_app(
        settings=settings,
        provider=cast(GenerationProvider, object()),
        store=MemoryChunkStore(),
    )

    assert app.state.tracer is app.state.ingestion.tracer is app.state.chat.tracer
