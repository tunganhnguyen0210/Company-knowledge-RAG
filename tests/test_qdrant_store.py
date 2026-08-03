from company_knowledge_rag.retrieval.qdrant_store import _point_id


def test_point_ids_are_stable_and_unique_for_chunks_in_same_document() -> None:
    first = _point_id("document:v1:0")
    second = _point_id("document:v1:1")

    assert first == _point_id("document:v1:0")
    assert first != second
