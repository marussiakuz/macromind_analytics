"""Knowledge repository tests (Task2 Stage A/B)."""

from osint_agent.knowledge.repository import KnowledgeRepository


def test_entity_upsert_no_duplicates():
    r = KnowledgeRepository(":memory:")
    a = r.upsert_entity("org", "ООО Тест", {"inn": "1"})
    b = r.upsert_entity("org", "ООО Тест", {"inn": "1"})
    assert a == b
    r.close()


def test_document_origin_dedupe():
    r = KnowledgeRepository(":memory:")
    d1 = r.add_document(source_type="web", url="https://a", title="A", origin_id="rep-1")
    d2 = r.add_document(source_type="web", url="https://b", title="B", origin_id="rep-1")
    assert d1 == d2
    r.close()


def test_evidence_and_text_search():
    r = KnowledgeRepository(":memory:")
    eid = r.upsert_entity("org", "X")
    r.add_evidence("Объем рынка 12 млрд", claim_type="fact", entity_id=eid, quote="12 млрд")
    r.add_evidence("Другой факт", entity_id=eid)
    hits = r.search_text("млрд")
    assert len(hits) == 1
    assert r.list_evidence(eid)
    r.close()
