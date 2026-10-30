"""Universal company check on multiple industries (acceptance, 2026-10-22).

Uses EXISTING pipeline steps with mocked network. No hardcoded competitors.
Covers: chemistry, software, equipment, services, no-site, multi-product.
"""

from __future__ import annotations

import pytest

from osint_agent.market.company_profile import (
    build_company_profile,
    extract_directions_from_text,
    score_official_site,
)
from osint_agent.market.universal_analysis import (
    completeness_status,
    gap_list,
    run_company_market_check,
)


class FakeRepo:
    def __init__(self):
        self.saved = []

    def save_analysis_version(self, summary, status="completed", request_key=None):
        row = {**summary, "analysis_version_id": f"v{len(self.saved)+1}", "status": status}
        self.saved.append(row)
        return row


async def _fake_collect_ok(company=None, **kwargs):
    return {
        "source_states": [{"source": "yandex_search", "status": "ok", "count": 2},
                          {"source": "openalex", "status": "ok", "count": 1}],
        "evidence": [
            {
                "id": "openalex:test1",
                "type": "scientific_work",
                "source_id": "openalex",
                "title": "Market study",
                "url": "https://doi.org/10.1/test",
                "doi": "10.1/test",
                "quote": "Объем рынка 42 млрд рублей в 2024. ООО ПолимерТех и ЗАО ХимПром — ключевые игроки.",
                "abstract": "Объем рынка 42 млрд рублей в 2024, рост 12%",
                "read_level": "abstract_only",
                "authors": ["Ivanov"],
                "publication_date": "2024-01-01",
                "completeness": "full",
                "limitations": ["Аннотация, не полная статья"],
            },
            {
                "id": "yandex:snip1",
                "type": "snippet",
                "source_id": "yandex_search",
                "title": "Company page",
                "url": "https://example.org",
                "quote": "ООО ПолимерТех поставляет оборудование",
                "read_level": "snippet_only",
                "limitations": ["Только выдержка поиска"],
            },
        ],
        "limitations": [],
    }


async def _fake_collect_down(company=None, **kwargs):
    return {
        "source_states": [{"source": "yandex_search", "status": "error", "count": 0}],
        "evidence": [],
        "limitations": ["Источники недоступны"],
    }


async def _fake_discovery(summary, workspace_id=None, fetch_externals=True):
    return {"discovered": True, "ingested": 2, "yandex_hits": 2, "openalex_works": 1,
            "limitations": [], "business_incognita": "requires_source_agreement"}


@pytest.fixture
def patch_stack(monkeypatch):
    monkeypatch.setattr(
        "osint_agent.market.evidence.collect_market_evidence",
        lambda company, llm_unused=None: _fake_collect_ok(),
    )
    monkeypatch.setattr(
        "osint_agent.market.auto_analysis.discover_reports_for_company",
        _fake_discovery,
    )
    monkeypatch.setattr(
        "osint_agent.market.auto_analysis.add_llm_interpretation_cached",
        lambda summary, llm=None: _wrap_llm(summary),
    )
    monkeypatch.setattr(
        "osint_agent.market.universal_analysis.fetch_site_text",
        lambda url, timeout=15.0: _fake_site(url),
    )
    from osint_agent.market.providers.base import SearchPage, SourceStatus
    class Search:
        async def search(self, *a, **k):
            return SearchPage(items=[], status=SourceStatus.empty)
        async def aclose(self): pass
    async def competitor_pages(*args): return [], []
    monkeypatch.setattr("osint_agent.market.universal_analysis._collect_competitor_product_pages", competitor_pages)
    async def read(items, **k): return items
    async def profile(company, evidence, llm):
        return {'product': company.get('product'), 'buyer': 'предприятия', 'about': 'Описание из источника'}
    async def interpret(summary, evidence, llm):
        return {'sections': {'russia': [{'text': 'Описание рынка из источника', 'evidence_ids': ['openalex:test1'], 'quotes': []}]},
                'competitors': {'russia': [{'name': 'ПолимерТех', 'specialization': 'Поставляет оборудование', 'why_competes': 'Оборудование для промышленных предприятий', 'quotes': [{'evidence_id': 'yandex:snip1', 'quote': 'ООО ПолимерТех поставляет оборудование'}]}], 'world': []}}
    monkeypatch.setattr('osint_agent.market.providers.web_search.YandexSearchProvider', Search)
    monkeypatch.setattr('osint_agent.market.universal_analysis._read_sources', read)
    monkeypatch.setattr('osint_agent.market.analytical_report.infer_product_profile', profile)
    monkeypatch.setattr('osint_agent.market.analytical_report.interpret_market_report', interpret)
    monkeypatch.setenv("KNOWLEDGE_DATABASE_URL", "")


async def _fake_site(url):
    return ("Компания производит полимеры и спецхимикаты для промышленных предприятий.", None)


async def _wrap_attach(summary, collect=None):
    pack = await (_fake_collect_ok() if collect is None else collect({}))
    summary = dict(summary)
    summary["external_source_states"] = pack["source_states"]
    summary["external_evidence"] = pack["evidence"]
    refs = list(summary.get("evidence_refs") or [])
    for e in pack["evidence"]:
        refs.append({
            "id": e["id"], "type": e.get("type"), "name": e.get("title"),
            "url": e.get("url"), "statement": e.get("quote") or e.get("title"),
            "quote": e.get("quote"), "source": e.get("source_id"),
            "read_level": e.get("read_level"), "doi": e.get("doi"),
            "authors": e.get("authors"), "publication_date": e.get("publication_date"),
        })
    summary["evidence_refs"] = refs
    return summary


def _wrap_llm(summary):
    s = dict(summary)
    s["llm_status"] = "ok"
    s["llm_summary"] = "Итог из принятых доказательств."
    s["llm_interpretation"] = [{"statement": "Объем рынка 42 млрд", "evidence_ids": ["openalex:test1"],
                                "claim_type": "fact", "verification_status": "needs_review"}]
    return s


def test_profile_chemistry_from_site_text():
    text = "ООО Химпром производит полимеры и специальные химикаты для промышленных предприятий."
    p = build_company_profile(
        {"inn": "7701", "name": "Химпром", "okved_main": "20.11",
         "okved_description": "Производство основных химических веществ"},
        site_text=text,
        known_urls=["https://chemprom.example/about"],
    )
    assert p.inn == "7701"
    assert p.directions, "product directions from site text"
    assert p.site_status in {"found", "verified", "ambiguous"}
    assert any("полимер" in d.name.lower() or "химикат" in d.name.lower() for d in p.directions)


def test_profile_software():
    text = "Компания разрабатывает платформу автоматизации и SaaS сервис для банков."
    p = build_company_profile(
        {"inn": "7802", "name": "СофтЛаб", "okved_description": "Разработка ПО"},
        site_text=text,
    )
    assert p.directions
    assert "SaaS" in text or "платформ" in text.lower()


def test_profile_equipment():
    text = "Предприятие изготавливает станки и промышленное оборудование для заводов."
    p = build_company_profile({"inn": "5903", "name": "Стан", "okved_description": "Производство оборудования"}, site_text=text)
    assert p.directions


def test_profile_services():
    text = "Оказываем консалтинговые услуги и логистические сервисы для B2B клиентов."
    p = build_company_profile({"inn": "7704", "name": "Сервис+", "okved_description": "Услуги"}, site_text=text)
    assert p.directions


def test_profile_no_site():
    p = build_company_profile({"inn": "1105", "name": "НетСайта", "okved_description": "Производство"})
    assert p.site_status == "not_found" or p.official_site is None
    assert "official_site" in p.gaps or p.site_status == "not_found"


def test_profile_multi_product():
    text = (
        "Производит реагенты. Поставляет оборудование. "
        "Внедряет программные решения для предприятий."
    )
    p = build_company_profile({"inn": "9906", "name": "Мульти"}, site_text=text)
    assert p.multi_product or len(p.directions) >= 2
    assert p.needs_product_clarification


def test_score_official_site_prefers_name_match():
    site, status, _ = score_official_site(
        "Химпром",
        ["https://forum.example/list", "https://chemprom.ru/"],
    )
    assert site and "chemprom" in site
    assert status in {"found", "verified"}


@pytest.mark.asyncio
async def test_universal_chemical_company(patch_stack):
    repo = FakeRepo()
    out = await run_company_market_check(
        inn="7701",
        company={"inn": "7701", "name": "Химпром", "okved_main": "20.11",
                 "okved_description": "Производство химических веществ",
                 "product": "полимеры", "buyer": "промышленные предприятия"},
        finances={"years": [{"year": 2024, "revenue": 100, "net_profit": 10}]},
        site_text="Производит полимеры для промышленных предприятий.",
        use_llm=True,
        repo=repo,
    )
    assert out["legal_entity_inn"] == "7701"
    assert out["completeness_status"] in {"full", "partial"}
    assert out["evidence_refs"], "OpenAlex/Yandex evidence attached"
    assert any(r.get("doi") or r.get("read_level") for r in out["evidence_refs"])
    assert out["analytical_report"]["competitors"]["russia"], "similar products from search"
    assert out.get("analytical_report"), "structured report"
    assert repo.saved and repo.saved[0]["analysis_version_id"]
    # no hardcoded competitor names
    blob = str(out).lower()
    for banned in ("primo rpa", "красный октябрь", "сбербанк"):
        assert banned not in blob


@pytest.mark.asyncio
async def test_universal_software_company(patch_stack):
    repo = FakeRepo()
    out = await run_company_market_check(
        inn="7802",
        company={"inn": "7802", "name": "СофтЛаб", "okved_description": "Разработка ПО",
                 "product": "платформа автоматизации"},
        finances={"years": [{"year": 2024, "revenue": 50, "net_profit": 5}]},
        site_text="SaaS платформа автоматизации для банков.",
        use_llm=True,
        repo=repo,
    )
    assert out["completeness_status"] in {"full", "partial"}
    assert out["product_scope"]["product"]


@pytest.mark.asyncio
async def test_universal_needs_clarification_no_data(patch_stack, monkeypatch):
    async def empty(summary, collect=None):
        return summary

    monkeypatch.setattr("osint_agent.market.auto_analysis.attach_external_evidence", empty)
    out = await run_company_market_check(
        inn="1105",
        company={"inn": "1105", "name": "НетСайта", "okved_description": "Производство"},
        use_llm=False,
        use_external_evidence=False,
        use_discovery=False,
    )
    assert out["completeness_status"] in {"needs_clarification", "partial", "insufficient_data"}
    assert out["gap_list"]
    assert "product_confirmation" in out["gap_list"] or "official_site" in out["gap_list"]


@pytest.mark.asyncio
async def test_universal_source_error(monkeypatch):
    from osint_agent.market.providers.base import SearchPage, SourceStatus
    class Search:
        async def search(self, *a, **k): return SearchPage(items=[], status=SourceStatus.error)
        async def aclose(self): pass
    monkeypatch.setattr("osint_agent.market.providers.web_search.YandexSearchProvider", Search)
    async def down(summary, collect=None):
        summary = dict(summary)
        summary["external_source_states"] = [{"source": "yandex", "status": "error"}]
        summary["external_evidence"] = []
        return summary

    monkeypatch.setattr("osint_agent.market.auto_analysis.attach_external_evidence", down)
    monkeypatch.setattr("osint_agent.market.auto_analysis.add_llm_interpretation_cached", lambda s, llm=None: s)
    monkeypatch.setattr("osint_agent.market.auto_analysis.discover_reports_for_company",
                        lambda s, **k: {"discovered": False, "reason": "KNOWLEDGE_DATABASE_URL is not set"})
    monkeypatch.setenv("KNOWLEDGE_DATABASE_URL", "")
    out = await run_company_market_check(
        inn="0000",
        company={"inn": "0000"},
        use_llm=False,
    )
    assert out["completeness_status"] in {"source_error", "needs_clarification", "partial", "insufficient_data"}
    assert out.get("errors") is not None


def test_completeness_helpers():
    s = {
        "external_source_states": [{"status": "ok"}],
        "evidence_refs": [{"id": "e1"}],
        "finance_summary": {"latest_year": {"year": 2024}},
        "product_scope": {"product": "полимеры", "product_status": "inferred_from_website",
                          "product_source": "website"},
    }
    assert completeness_status(s) == "full"
    s["product_scope"]["product_status"] = "needs_clarification"
    s["product_scope"]["product_source"] = None
    assert completeness_status(s) == "partial"
    g = gap_list(s, "partial")
    assert "product_from_website" in g


@pytest.mark.asyncio
@pytest.mark.parametrize('product', ['Скважинные датчики', 'Химические реакторы', 'Программное обеспечение'])
async def test_crawled_product_pages_reach_profile_and_interpretation(patch_stack, monkeypatch, product):
    page={'id':'company-page:product','title':'Продукция','url':'https://company.example/product',
          'quote':f'{product} для промышленных заказчиков. Подробности доступны в каталоге компании.',
          'read_level':'page_excerpt'}
    seen=[]
    async def research(*args,**kwargs):
        return {'source_evidence':[page],'directions':[],'official_site':'https://company.example'}
    async def profile(company,evidence,llm):
        assert page in evidence
        seen.append('profile')
        return {'product':product,'buyer':'Промышленные предприятия','evidence_ids':[page['id']]}
    async def interpret(summary,evidence,llm):
        assert page in evidence
        assert summary['product_scope']['product']==product
        seen.append('interpret')
        return {'sections':{},'competitors':{}}
    monkeypatch.setattr('osint_agent.market.universal_analysis.research_company_profile',research)
    monkeypatch.setattr('osint_agent.market.analytical_report.infer_product_profile',profile)
    monkeypatch.setattr('osint_agent.market.analytical_report.interpret_market_report',interpret)
    result=await run_company_market_check(inn='123',company={'inn':'123','name':'Новая компания'},repo=FakeRepo())
    assert seen==['profile','interpret']
    assert page in result['external_evidence']
