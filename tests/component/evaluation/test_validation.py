from pathlib import Path

from domain.schemas import Document, DocumentStatus
from evaluation.golden import load_golden_dataset, validate_golden_dataset
from ingestion.chunker import chunk_document
from ingestion.parser import parse_document


def test_real_docx_chunks_recover_all_answerable_golden_evidence() -> None:
    raw_path = Path("data/raw/01_2021_ND-CP_283247.docx")
    parsed_text, mime_type = parse_document(raw_path.name, raw_path.read_bytes())
    document = Document(
        id="offline-eval-document",
        version=1,
        content_hash="fixture-hash",
        source_name=raw_path.name,
        mime_type=mime_type,
        status=DocumentStatus.READY,
        metadata={"canonical_doc_id": "01_2021_ND-CP_283247.md"},
    )
    chunks = chunk_document(document, parsed_text)
    report = validate_golden_dataset(
        load_golden_dataset(Path("evaluation/golden_set")),
        canonical_path=Path("data/extracted/01_2021_ND-CP_283247.md"),
        chunks=chunks,
        audit_root=Path("evaluation"),
    )

    assert not {
        issue.case_id
        for issue in report.errors
        if issue.code == "context_not_recoverable_from_chunks"
    }
