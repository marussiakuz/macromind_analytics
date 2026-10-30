"""Tests: discovery queries, DOI dedup, fetch SSRF, Incognita readiness, A/B scoring."""

from __future__ import annotations

import pytest

from osint_agent.knowledge.connectors.incognita import (
    STATUS,
    BusinessIncognitaConnector,
    IncognitaConnectorConfig,
)
from osint_agent.knowledge.discovery.fetch import assert_public_url
from osint_agent.knowledge.discovery.openalex_collect import parse_work
from osint_agent.knowledge.discovery.queries import ProductProfile, build_queries, openalex_search_terms


def test_queries_ru_en_from_product_profile():
    p = ProductProfile(product="RPA", geography="Россия", buyers="банки", year_from=2024, year_to=2026)
    qs = build_queries(p)
    langs = {q["lang"] for q in qs}
    assert "ru" in langs and "en" in langs
    blob = " ".join(q["query"] for q in qs)
    assert "RPA" in blob
    assert "filetype:pdf" in blob  # extra query, not mandatory filter
    assert openalex_search_terms(p)


def test_parse_work_doi_and_read_level():
    rec = parse_work({
        "id": "https://openalex.org/W1",
        "doi": "https://doi.org/10.1234/abc",
        "title": "RPA market",
        "authorships": [{"author": {"display_name": "Ivanov"}}],
        "publication_date": "2025-03-01",
        "abstract_inverted_index": {"RPA": [0], "grows": [1]},
        "cited_by_count": 42,
        "open_access": {"oa_url": "https://example.org/paper.pdf"},
    })
    assert rec.doi == "10.1234/abc"
    assert rec.read_level == "abstract_only"
    assert rec.authors == ["Ivanov"]
    assert rec.full_text_url.endswith("paper.pdf")
    assert "RPA" in (rec.abstract or "")


def test_parse_work_normalizes_doi_forms():
    a = parse_work({"id": "W1", "doi": "doi:10.1/x"})
    b = parse_work({"id": "W1", "doi": "https://doi.org/10.1/X"})
    assert a.doi == b.doi == "10.1/x"


def test_fetch_blocks_internal_and_bad_schemes():
    from osint_agent.knowledge.discovery.fetch import FetchError
    with pytest.raises(FetchError):
        assert_public_url("file:///etc/passwd")
    with pytest.raises(FetchError):
        assert_public_url("http://127.0.0.1/x")
    with pytest.raises(FetchError):
        assert_public_url("http://169.254.169.254/latest/meta-data/")


def test_incognita_requires_source_agreement():
    c = BusinessIncognitaConnector(IncognitaConnectorConfig(enabled=False))
    ready = c.readiness()
    assert ready["status"] == STATUS
    assert ready["live_enabled"] is False
    assert any("api_id" in m for m in ready["missing"])
    assert any("согласие" in a.lower() or "consent" in a.lower() or "Telegram" in a for a in ready["required_access"])
    with pytest.raises(PermissionError):
        import asyncio as aio
        aio.run(c.fetch_history("not_on_list", limit=1))
    c2 = BusinessIncognitaConnector(
        IncognitaConnectorConfig(enabled=False, channel_allowlist=["business_incognita"])
    )
    with pytest.raises(RuntimeError):
        import asyncio as aio
        aio.run(c2.fetch_history("business_incognita", limit=1))


def test_incognita_fixture_parse():
    c = BusinessIncognitaConnector(IncognitaConnectorConfig(enabled=False))
    m = c.parse_fixture({"channel_id": "c1", "message_id": 7, "date": "2026-01-01",
                         "text": "Отчет https://example.org/r.pdf", "urls": ["https://example.org/r.pdf"]})
    assert m.message_id == 7
    assert m.urls


def test_ab_empty_positive_is_miss():
    """§6.5: empty retrieval on answerable question must count as 0.0."""
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location(
        "ab", Path(__file__).resolve().parents[2] / "scripts" / "incognita_ingest_ab.py"
    )
    ab = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ab)

    class FakeRetriever:
        def __init__(self, *a, **k):
            self.embed_fn = None
        def retrieve(self, *a, **k):
            class R:
                items = []
                empty_reason = "no_evidence_in_allowed_corpus"
            return R()

    ab.EvidenceRetriever = FakeRetriever
    ab.embed_q = lambda q: []
    out = ab.score_set(
        None,
        [{"id": "q1", "question": "x", "answerable": True, "relevant_titles": ["Doc"]}],
        "ws",
        label="t",
    )
    assert out["recall"] == 0.0  # miss, not None
