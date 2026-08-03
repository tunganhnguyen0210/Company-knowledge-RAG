from __future__ import annotations

import json
import threading
from pathlib import Path

from company_knowledge_rag.domain.schemas import Document


class DocumentRegistry:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()

    def list(self) -> list[Document]:
        if not self.path.exists():
            return []
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return [Document.model_validate(item) for item in data]

    def get(self, document_id: str) -> Document | None:
        return next((item for item in self.list() if item.id == document_id), None)

    def find_by_source(self, source_name: str) -> Document | None:
        return next((item for item in self.list() if item.source_name == source_name), None)

    def upsert(self, document: Document) -> None:
        with self._lock:
            documents = self.list()
            documents = [item for item in documents if item.id != document.id]
            documents.append(document)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(
                json.dumps([item.model_dump(mode="json") for item in documents], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            temporary.replace(self.path)

