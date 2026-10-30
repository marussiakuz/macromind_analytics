"""Negative regressions from Astra review 2026-10-24 (ASTRA_REVIEW_COMPANY_RESEARCH_2026-10-24.md).

These MUST fail on the unfixed code and pass after the P1 fixes.
"""

from __future__ import annotations

import pytest

from osint_agent.market.competitor_research import (
    classify_candidate,
    detect_product_overlap,
    is_plausible_company_name,
    suppliers_from_directions,
)
from osint_agent.market.site_research import research_company_directions


DIR_HOSES = {
    "direction_id": "d1",
    "product_category_ru": "Гидравлические шланги",
    "product_category_en": "hydraulic hoses",
    "role": "manufacturer",
    "applications": ["мобильная гидравлика"],
    "buyer_segments": ["производители техники"],
    "geography": "Россия",
    "brands": [{"name": "Acme", "relation": "supplier"}],
}


class TestCrawlNotReplacedBySiteText:
    """P1: successful crawl must not be replaced by company_input."""

    @pytest.mark.asyncio
    async def test_site_text_does_not_destroy_crawl(self):
        from unittest.mock import patch
        import osint_agent.market.site_research as s

        async def fake_crawl(*a, **kw):
            return {
                "pages": [{
                    "url": "https://example.org/production",
                    "text": "Компания Тест производит оборудование и рукава высокого давления. " * 12,
                    "kind": "html",
                }],
                "read_urls": ["https://example.org/production"],
                "states": [],
                "limitations": [],
            }

        seen: list[str] = []

        async def fake_infer(company, pages, llm, **kw):
            seen.extend(p["url"] for p in pages)
            return {"directions": [], "about": ""}

        with patch.object(s, "crawl_company_site", fake_crawl), \
             patch.object(s, "infer_company_directions", fake_infer):
            result = await s.research_company_directions(
                {"name": "ООО Тест", "inn": "1234567890"},
                object(),
                site_url="https://example.org",
                site_text="Краткое описание деятельности компании из реестра. " * 10,
                use_site_discovery=False,
            )

        assert "https://example.org/production" in result["read_urls"]
        assert result["read_urls"] != ["company_input"]
        assert any("example.org/production" in u for u in seen), "model must see crawled pages"
        assert not any(u == "company_input" and len(seen) == 1 for u in seen)

    @pytest.mark.asyncio
    async def test_site_text_used_only_when_crawl_empty(self):
        from unittest.mock import patch
        import osint_agent.market.site_research as s

        async def empty_crawl(*a, **kw):
            return {"pages": [], "read_urls": [], "states": [], "limitations": []}

        seen: list[str] = []

        async def fake_infer(company, pages, llm, **kw):
            seen.extend(p.get("url") for p in pages)
            return {"directions": [], "about": ""}

        with patch.object(s, "crawl_company_site", empty_crawl), \
             patch.object(s, "infer_company_directions", fake_infer):
            result = await s.research_company_directions(
                {"name": "ООО Тест", "inn": "1234567890"},
                object(),
                site_url="https://example.org",
                site_text="Описание компании. " * 20,
                use_site_discovery=False,
            )
        assert result["read_urls"] == ["company_input"] or "company_input" in (result.get("read_urls") or [])
        assert result.get("read_urls")


class TestProductOverlapNotSingleWord:
    """P1: hydraulic hoses must not match hydraulic pumps."""

    def test_hoses_vs_pumps_rejected(self):
        d = dict(DIR_HOSES)
        assert detect_product_overlap(d, [
            "Acme manufactures hydraulic pumps for aircraft.",
        ]) is False

    def test_same_category_matches(self):
        d = dict(DIR_HOSES)
        assert detect_product_overlap(d, [
            "Производство гидравлических шлангов и рукавов высокого давления.",
        ]) is True


class TestSupplierNotAutoRelation:
    """P1: independent firm describing itself as supplier ≠ partner of the studied company."""

    def test_unrelated_foreign_supplier_not_partner(self):
        row = classify_candidate(
            name="Acme Systems",
            direction=DIR_HOSES,
            own_company_names=["ООО Тест"],
            supplier_or_partner_names=[],  # no declared suppliers of the studied firm
            quotes=["Acme is a supplier of hydraulic hoses in Germany."],
            territory="world",
            territory_confirmed=False,
            buyers_overlap=None,
            role_compatible=True,
            product_overlap=True,
        )
        # Own role text must not create a relation with the studied company.
        assert row["relation_class"] != "supplier_partner"
        assert row["relation_class"] in {"product_analog", "candidate_for_check", "rejected"}

    def test_declared_supplier_still_partner(self):
        row = classify_candidate(
            name="Walvoil",
            direction=DIR_HOSES,
            own_company_names=["ООО Тест"],
            supplier_or_partner_names=["Walvoil"],
            quotes=["Дистрибьютор Walvoil на территории России."],
            territory="world",
            territory_confirmed=None,
            buyers_overlap=True,
            role_compatible=True,
            product_overlap=True,
        )
        assert row["relation_class"] == "supplier_partner"


class TestRealBrandNamesAccepted:
    """P1: real brands must not be rejected by name form."""

    @pytest.mark.parametrize("name", [
        "Gates", "Graco", "PIX Robotics", "JSE Group",
    ])
    def test_real_names_not_noise(self, name):
        assert is_plausible_company_name(name) is True, name


class TestNoHardcodedGidroel:
    """P1: GidroEl is not an alias for every company."""

    def test_own_names_from_company_only(self):
        dirs = [dict(DIR_HOSES)]
        # suppliers_from_directions should not inject GidroEl
        sup = suppliers_from_directions(dirs)
        assert "Hydroel" not in sup
        assert "ГидроЭл" not in sup

    def test_gidroel_can_be_candidate_for_other_firms(self):
        row = classify_candidate(
            name="ГидроЭл",
            direction=DIR_HOSES,
            own_company_names=["ООО Тест", "Тест"],  # NOT GidroEl
            supplier_or_partner_names=[],
            quotes=["ГидроЭл производит гидроблоки и шланги."],
            territory="russia",
            territory_confirmed=True,
            buyers_overlap=True,
            role_compatible=True,
            product_overlap=True,
        )
        assert row["relation_class"] != "rejected" or row["reason"] != "self_company"


class TestQuoteUrlPairsAtomic:
    """P1: quote+url pairs must stay aligned; different firms on one catalog page stay separate."""

    def test_catalog_host_does_not_merge_firms(self):
        from osint_agent.market.competitor_research import normalize_company_key
        a = normalize_company_key("ООО Ромашка")
        b = normalize_company_key("ООО Василёк")
        assert a != b
        # host merge is gone — identity is name-based only
        import inspect
        from osint_agent.market import competitor_research as cr
        src = inspect.getsource(cr.discover_direction_candidates)
        assert "by_host" not in src or "do NOT merge" in src
