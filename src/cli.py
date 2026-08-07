from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn

from api.app import create_app
from settings import Settings
from storage.reconcile import purge_orphans, reconcile


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


def reconcile_index() -> None:
    parser = argparse.ArgumentParser(
        description="Compare the vector index against the registry and report orphaned chunks"
    )
    parser.add_argument(
        "--purge",
        action="store_true",
        help="Delete orphaned chunks (documents absent from the registry). Destructive.",
    )
    parser.add_argument("--yes", action="store_true", help="Skip the confirmation prompt")
    args = parser.parse_args()
    settings = Settings()
    app = create_app(settings)
    registry, store = app.state.registry, app.state.store

    report = reconcile(registry, store)
    print(f"collection      : {settings.qdrant_collection}")
    print(f"registry docs   : {len(report.registered)}")
    print(f"indexed docs    : {len(report.indexed)}")
    print(f"indexed chunks  : {sum(report.indexed.values())}")

    if report.missing:
        print(f"\nMISSING from index ({len(report.missing)}) - re-ingest these, never purge:")
        for document_id, source_name in sorted(report.missing.items(), key=lambda item: item[1]):
            print(f"  {source_name}  ({document_id})")

    if not report.orphans:
        print("\nNo orphaned chunks.")
        return

    print(f"\nORPHANED ({len(report.orphans)} documents, {report.orphan_chunk_count} chunks) "
          "- present in the index but absent from the registry:")
    for document_id, count in sorted(report.orphans.items(), key=lambda item: -item[1]):
        print(f"  {document_id}  {count} chunks")

    if not args.purge:
        print("\nRe-run with --purge to delete them.")
        return
    if not args.yes:
        answer = input(f"\nDelete {report.orphan_chunk_count} chunks from "
                       f"{settings.qdrant_collection}? [y/N] ")
        if answer.strip().lower() not in {"y", "yes"}:
            print("Aborted.")
            return
    _, removed = purge_orphans(registry, store)
    print(f"Removed {removed} orphaned chunks.")


def ingest() -> None:
    parser = argparse.ArgumentParser(description="Ingest a file or directory")
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    settings = Settings()
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

