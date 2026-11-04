"""Stage A: site verification, bounded crawl, directions with evidence."""

from __future__ import annotations

import pytest

from osint_agent.market.site_research import (
    categorize_link,
    direction_record,
    html_to_text,
    normalize_url,
    priority_key,
    quotes_for_evidence_ids,
    verify_site_ownership,
)


class TestNormalizeUrl:
    def test_drops_fragment_and_tracking(self):
        u = normalize_url("https://www.example.ru/Products/?utm_source=x&fbclid=1#top")
        assert u == "https://example.ru/Products/"

    def test_rejects_bad_scheme(self):
        assert normalize_url("ftp://example.ru/x") is None
        assert normalize_url("javascript:void(0)") is None


class TestCategorizeLink:
    def test_production_priority(self):
        assert categorize_link("https://x.ru/proizvodstvo/", "Производство") == "production"

    def test_pdf(self):
        assert categorize_link("https://x.ru/files/catalog.pdf", "Каталог") == "pdf"

    def test_unknown(self):
        assert categorize_link("https://x.ru/misc/page", "x") == "other"


class TestPriorityKey:
    def test_production_before_other(self):
        seen = set()
        prod = priority_key("production", 1, seen)
        other = priority_key("other", 1, seen)
        assert prod < other

    def test_unseen_category_preferred(self):
        seen = {"catalog"}
        unseen_prod = priority_key("production", 1, seen)
        seen_catalog = priority_key("catalog", 1, seen)
        assert unseen_prod < seen_catalog


class TestHtmlToText:
    def test_strips_script_and_tags(self):
        text = html_to_text("<html><script>evil()</script><body><p>Продукция</p></body></html>")
        assert "Продукция" in text
        assert "evil" not in text


class TestVerifySite:
    def _company(self):
        return {
            "inn": "5040133380",
            "ogrn": "1145040011522",
            "name": "ГидроЭл",
            "full_name": "ООО «ГидроЭл»",
            "contacts": {
                "ВебСайт": "https://gidroel.ru",
                "Телефон": "+7 (812) 555-12-34",
                "ЭлектроннаяПочта": "info@gidroel.ru",
            },
        }

    def test_verified_with_inn_on_site(self):
        page = (
            "ООО ГидроЭл. ИНН 5040133380. ОГРН 1157847001234. "
            "Телефон +7 (812) 555-12-34. Производство гидравлических рукавов."
        )
        result = verify_site_ownership(self._company(), "https://gidroel.ru", [page])
        assert result.status == "verified"
        assert result.matched_signals.get("inn_on_site") is True
        assert result.site and "gidroel" in result.site

    def test_verified_with_ogrn_on_site(self):
        result = verify_site_ownership(
            self._company(), "https://gidroel.ru",
            ["Контакты. ОГРН 1145040011522. Телефон +7 (812) 555-12-34. "
             "ООО ГидроЭл. Реквизиты компании."],
        )
        assert result.status == "verified"
        assert result.matched_signals.get("ogrn_on_site") is True

    def test_name_only_is_not_verified(self):
        result = verify_site_ownership(
            self._company(), "https://gidroel.ru",
            ["ГидроЭл — компания на рынке. Ничего больше нет."],
        )
        assert result.status in {"probable", "ambiguous"}
        assert result.status != "verified"

    def test_no_url(self):
        result = verify_site_ownership({"inn": "1", "name": "X"}, None, [])
        assert result.status == "not_found"

    def test_foreign_inn_lowers_confidence(self):
        page = "ИНН 7707083893. Другая фирма. ГидроЭл упоминается в каталоге."
        result = verify_site_ownership(self._company(), "https://gidroel.ru", [page])
        assert result.status in {"ambiguous", "probable"}
        assert result.matched_signals.get("other_inns_on_site")


class TestDirectionRecord:
    def test_unknown_role_kept(self):
        rec = direction_record(
            direction_id="d1",
            product_category_ru="Шланги гидравлические",
            role="not_a_role",
            status="supported",
        )
        assert rec["role"] == "unknown"
        assert rec["status"] == "supported"

    def test_quotes_attached_from_server(self):
        passages = {
            "P1": {"id": "P1", "text": "Мы производим рукава высокого давления",
                   "url": "https://x.ru/about", "title": "О заводе", "read_level": "page_excerpt"},
        }
        quotes = quotes_for_evidence_ids(["P1", "P9"], passages)
        assert len(quotes) == 1
        assert "производим" in quotes[0]["quote"]
        assert quotes[0]["url"] == "https://x.ru/about"


class TestInferDirectionsRules:
    @pytest.mark.asyncio
    async def test_manufacturer_without_production_quote_is_downgraded(self):
        from osint_agent.market.site_research import infer_company_directions

        class FakeLLM:
            async def complete(self, prompt, payload, json_schema=None):
                class R:
                    ok = True
                    error = None
                    text = (
                        '{"directions":[{"direction_id":"d1",'
                        '"product_category_ru":"Шланги",'
                        '"product_category_en":"Hoses","role":"manufacturer",'
                        '"applications":["гидравлика"],"buyer_segments":[],'
                        '"geography":"unknown","brands":[],'
                        '"evidence_ids":["P1"],"status":"supported","limitations":[]}],'
                        '"about":"test"}'
                    )
                return R()

        pages = [{
            "url": "https://x.ru/catalog",
            "title": "Каталог",
            "text": (
                "В наличии шланги и рукава высокого давления различного диаметра. "
                "Доставка по России. Складская программа. Каталог продукции компании."
            ),
        }]
        out = await infer_company_directions({"name": "Тест", "inn": "1"}, pages, FakeLLM())
        assert out.get("directions"), out
        d = out["directions"][0]
        # catalog stock text does not prove own production
        assert d["role"] != "manufacturer"
        assert d["status"] in {"hypothesis", "unresolved", "supported"}
        assert any("производ" in lim.lower() or "снижена" in lim.lower() for lim in d["limitations"])


class TestSiteQuality:
    def test_empty_stub_detected(self):
        from osint_agent.market.site_research import assess_site_quality
        q = assess_site_quality([{"text": "", "fetch_status": "ok"}], "")
        assert q["kind"] == "empty_or_stub"
        assert q["usable"] is False

    def test_parked_domain_detected(self):
        from osint_agent.market.site_research import assess_site_quality
        q = assess_site_quality(
            [{"text": "NNOV Домены в зоне .nnov.ru", "fetch_status": "ok"}],
            "<html>names.nnov.ru domain for sale</html>",
        )
        assert q["kind"] == "parked_or_registrar"
        assert any("припаркован" in n.lower() for n in q["notes"])

    def test_healthy_site_usable(self):
        from osint_agent.market.site_research import assess_site_quality
        q = assess_site_quality(
            [{"text": "Компания производит гидроблоки и рукава высокого давления " * 5, "fetch_status": "ok"}],
            "",
        )
        assert q["kind"] == "ok"
        assert q["usable"] is True


def test_product_pages_preserve_read_content_for_downstream_analysis():
    from osint_agent.market.site_research import company_page_evidence
    text='Компания создаёт скважинные датчики температуры и давления. Системы передают измерения на поверхность скважины.'
    rows=company_page_evidence([
        {'url':'https://company.example/product?utm_source=x','text':'Короткий текст'},
        {'url':'https://company.example/product','text':text,'title':'Скважинные системы'},
        {'url':'https://company.example/product','text':text},
        {'url':'javascript:alert(1)','text':text},
    ])
    assert len(rows)==1
    assert rows[0]['quote']==text
    assert rows[0]['url']=='https://company.example/product'
    assert rows[0]['read_level']=='page_excerpt'
    assert rows[0]['full_text_read'] is False


def test_unrelated_search_snippet_cannot_define_company_business():
    from osint_agent.market.site_research import snippet_matches_company
    company = {'inn': '7725438098', 'name': 'ООО "КОУЛМЭН ГРУП"', 'website': 'https://coleman.ru'}
    assert not snippet_matches_company(company, 'https://games.example', 'Дистрибуция Lineage 2 и Black Desert')
    assert snippet_matches_company(company, 'https://www.coleman.ru/services', 'Кадровые услуги')
    assert snippet_matches_company(company, 'https://news.example', 'ООО Коулмэн Груп подбирает персонал')
    assert snippet_matches_company(company, 'https://registry.example', 'ИНН 7725438098 кадровые услуги')
