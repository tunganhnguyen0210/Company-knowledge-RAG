from __future__ import annotations

import argparse
import json
from pathlib import Path

import uvicorn

from api.app import create_app
from evaluation.runner import run_golden_set
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
    parser = argparse.ArgumentParser(description="Ingest a file or directory")
    parser.add_argument("path", type=Path)
    parser.add_argument("--roles", required=True, help="Comma-separated ACL roles")
    args = parser.parse_args()
    settings = Settings()
    app = create_app(settings)
    roles = {role.strip() for role in args.roles.split(",") if role.strip()}
    paths = sorted(args.path.iterdir()) if args.path.is_dir() else [args.path]
    for path in paths:
        if path.suffix.lower() not in {".md", ".txt", ".pdf", ".docx"}:
            continue
        document = app.state.ingestion.ingest_bytes(path.name, path.read_bytes(), roles)
        print(f"{document.source_name}: {document.status} v{document.version} ({document.id})")


def evaluate() -> None:
    parser = argparse.ArgumentParser(description="Run golden-set regression evaluation")
    parser.add_argument("--dataset", type=Path, default=Path("evaluation/golden_set.json"))
    parser.add_argument("--output", type=Path, default=Path("reports/golden_report.json"))
    args = parser.parse_args()
    app = create_app(Settings())
    report = run_golden_set(app.state.chat, args.dataset)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["aggregate"], ensure_ascii=False, indent=2))

