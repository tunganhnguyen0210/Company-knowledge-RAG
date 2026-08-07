from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn

from api.app import create_app
from settings import Settings


def serve() -> None:
    parser = argparse.ArgumentParser(description="Run the Company Knowledge RAG API")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()
    uvicorn.run(
        "api.app:app_factory",
        factory=True,
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


def ingest() -> None:
    settings = Settings()
    parser = argparse.ArgumentParser(description="Ingest a file or directory")
    parser.add_argument(
        "path",
        type=Path,
        nargs="?",
        default=getattr(settings, "raw_dir", Path("data/raw")),
        help="Path to file or directory to ingest (defaults to data/raw)",
    )
    args = parser.parse_args()
    app = create_app(settings)
    try:
        paths = sorted(args.path.iterdir()) if args.path.is_dir() else [args.path]
        for path in paths:
            if path.suffix.lower() not in {".md", ".txt", ".pdf", ".docx"}:
                continue
            document = app.state.ingestion.ingest_bytes(path.name, path.read_bytes())
            print(f"{document.source_name}: {document.status} v{document.version} ({document.id})")
    except BaseException:
        try:
            app.state.tracer.flush()
        except BaseException:
            pass
        raise
    else:
        app.state.tracer.flush()

