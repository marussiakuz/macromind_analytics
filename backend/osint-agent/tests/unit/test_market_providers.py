"""Provider adapters and competitor/VRIO tests (plan §7, §12, §21)."""

import base64
from decimal import Decimal

import httpx
import pytest

from osint_agent.market.competitors import (
    Competitor,
    VRIOAnswer,
    VRIOAssessment,
    VRIOCell,
    competitor_table,
    findings_summary,
    interpret_vrio,
    select_competitors,
)
from osint_agent.market.providers.base import SourceStatus
from osint_agent.market.providers.openalex import OpenAlexProvider, rebuild_abstract
from osint_agent.market.providers.web_search import YandexSearchProvider, _safe_xml
from osint_agent.market.technology import EvidenceType, TechnologyEvidence, merge_publications


# --- OpenAlex ---

def test_p10_abstract_inverted_index():
    text = rebuild_abstract({"world": [1], "hello": [0]})
    assert text == "hello world"


def test_p09_missing_abstract_is_none():
    assert rebuild_abstract(None) is None
    assert rebuild_abstract({}) is None


def test_abstract_bad_position_raises():
    with pytest.raises(ValueError):
        rebuild_abstract({"x": [-1]})
    with pytest.raises(ValueError):
        rebuild_abstract({"x": "nope"})


@pytest.mark.asyncio
async def test_openalex_not_configured():
    p = OpenAlexProvider(api_key="")
    page = await p.search("test query")
    assert page.status == SourceStatus.not_configured
    assert page.items == []


@pytest.mark.asyncio
async def test_openalex_parses_results_and_missing_abstract():
    payload = {
        "meta": {"next_cursor": "c1"},
        "results": [
            {
                "id": "https://openalex.org/W1",
                "doi": "https://doi.org/10.1/x",
                "title": "Work",
                "publication_date": "2024-01-01",
                "abstract_inverted_index": None,
                "cited_by_count": 3,
                "authorships": [],
                "primary_location": None,
            }
        ],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("Authorization") == "Bearer test-key"
        assert "api_key=" not in str(request.url)
        return httpx.Response(200, json=payload)

    p = OpenAlexProvider(api_key="test-key", client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    try:
        page = await p.search("batteryless sensors")
    finally:
        await p.aclose()
    assert page.status == SourceStatus.ok
    assert page.items[0]["abstract"] is None
    assert page.items[0]["doi"].endswith("10.1/x")
    assert page.cursor == "c1"


@pytest.mark.asyncio
async def test_openalex_rate_limit():
    def handler(request):
        return httpx.Response(429)

    p = OpenAlexProvider(api_key="k", client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    try:
        page = await p.search("q")
    finally:
        await p.aclose()
    assert page.status == SourceStatus.rate_limited


# --- Yandex ---

def _xml_doc(url, title, passage):
    return f"<doc><url>{url}</url><title>{title}</title><passage>{passage}</passage></doc>"


def test_p07_title_with_nested_markup():
    xml = f"<yandexsearch>{_xml_doc('https://a.ru', '<hl>Bo</hl>ld', 'text')}</yandexsearch>"
    docs = _safe_xml(xml)
    assert docs[0]["title"] == "Bold"


@pytest.mark.asyncio
async def test_p08_page_number_passed():
    captured = {}

    def handler(request):
        import json

        captured["body"] = json.loads(request.content)
        raw = base64.b64encode(
            f"<yandexsearch>{_xml_doc('https://a.ru', 'T', 'P')}</yandexsearch>".encode()
        ).decode()
        return httpx.Response(200, json={"rawData": raw})

    p = YandexSearchProvider(
        api_key="k", folder_id="f", client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    try:
        page = await p.search("q", cursor="1", budget=5)
    finally:
        await p.aclose()
    assert captured["body"]["query"]["page"] == "1"
    assert page.items[0]["url"] == "https://a.ru"


@pytest.mark.asyncio
async def test_p06_missing_rawdata_is_error():
    def handler(request):
        return httpx.Response(200, json={})

    p = YandexSearchProvider(
        api_key="k", folder_id="f", client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    try:
        page = await p.search("q")
    finally:
        await p.aclose()
    assert page.status == SourceStatus.error
    assert "rawData" in page.message


@pytest.mark.asyncio
async def test_yandex_bad_base64_is_error():
    def handler(request):
        return httpx.Response(200, json={"rawData": "!!!"})

    p = YandexSearchProvider(
        api_key="k", folder_id="f", client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    try:
        page = await p.search("q")
    finally:
        await p.aclose()
    assert page.status == SourceStatus.error


# --- Competitors / VRIO ---

def test_v02_three_competitors_shown_with_incompleteness():
    cands = [
        {"company_name": f"C{i}", "product_name": f"P{i}"} for i in range(3)
    ]
    inc, exc = select_competitors(cands)
    assert len(inc) == 3
    findings = findings_summary(inc, exc)
    assert findings.incompleteness_note is not None
    assert "3" in findings.incompleteness_note


def test_v01_unknown_vrio_no_final_advantage():
    a = VRIOAssessment(
        competitor_id=Competitor(company_name="X", product_name="Y").id,
        resource="dataset",
        v=VRIOCell(answer=VRIOAnswer.yes),
        r=VRIOCell(answer=VRIOAnswer.yes),
        i=VRIOCell(answer=VRIOAnswer.yes),
        o=VRIOCell(answer=VRIOAnswer.unknown),
    )
    text = interpret_vrio(a)
    assert "не подтверждено" in text.lower() or "недостаточно" in text.lower()


def test_vrio_all_yes():
    a = VRIOAssessment(
        competitor_id=Competitor(company_name="X", product_name="Y").id,
        resource="tech",
        v=VRIOCell(answer=VRIOAnswer.yes),
        r=VRIOCell(answer=VRIOAnswer.yes),
        i=VRIOCell(answer=VRIOAnswer.yes),
        o=VRIOCell(answer=VRIOAnswer.yes),
    )
    assert "устойчивого" in interpret_vrio(a)


def test_competitor_table_price_on_request_is_unknown():
    from osint_agent.market.competitors import FeatureAssessment

    c = Competitor(company_name="A", product_name="B")
    rows = competitor_table(
        [c],
        [FeatureAssessment(competitor_id=c.id, feature="price", value_numeric=None, evidence="по запросу")],
    )
    assert rows[0]["features"]["price"]["value"] is None


def test_p04_publications_merged_by_doi():
    a = TechnologyEvidence(kind=EvidenceType.publication, external_id="10.1/x", url="https://1", title="T")
    b = TechnologyEvidence(kind=EvidenceType.publication, external_id="10.1/x", url="https://2", title="T copy")
    merged = merge_publications([a, b])
    assert len(merged) == 1
    assert "https://2" in merged[0].raw.get("alt_urls", [])
