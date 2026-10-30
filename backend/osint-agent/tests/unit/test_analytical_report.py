"""Analytical report structure (Gazprombank-style) without legal cases."""

from osint_agent.market.analytical_report import (
    build_analytical_report,
    extract_company_names_from_evidence,
    render_analytical_report_html,
)


def test_report_has_reference_sections():
    summary = {
        "legal_entity_inn": "5040133380",
        "product_scope": {
            "product": "гидрооборудование",
            "buyer": "предприятия",
            "okved": "46.69",
            "okved_description": "Торговля оптовая прочими машинами и оборудованием",
        },
        "finance_summary": {"latest_year": {"year": 2024, "revenue": 120000000, "net_profit": 8000000}},
        "data_completeness": {"last_revenue": {"year": 2024, "revenue": 120000000, "net_profit": 8000000}},
        "evidence_refs": [
            {
                "id": "e1",
                "title": "Рынок гидрооборудования",
                "quote": "Объем рынка 42 млрд рублей в 2024. Linde plc и Air Liquide — лидеры.",
                "source": "yandex_search",
            }
        ],
        "related_organizations": [
            {"name": "ООО Ремавтоснаб", "roles": ["ответчик"]},
            {"name": "АО ЗЛАТМАШ", "roles": ["заказчик"]},
        ],
        "competitor_candidates": [{"name": "АО ЗЛАТМАШ", "status": "candidate_for_check"}],
        "limitations": ["Оценка не является инвестиционной рекомендацией."],
    }
    r = build_analytical_report(summary, company_name="ГИДРОЭЛ ИНЖИНИРИНГ", inn="5040133380")
    assert r["company"]["name"] == "ГИДРОЭЛ ИНЖИНИРИНГ"
    assert r["finances"] and r["finances"][0]["year"] == 2024
    assert "world" in r["market"] and "russia" in r["market"]
    assert r["market"]["fragments"], "market numbers extracted"
    # legal parties excluded from related
    assert not any("Ремавтоснаб" in (x.get("name") or "") for x in r["related_business"])
    assert any("ЗЛАТМАШ" in (x.get("name") or "") for x in r["related_business"])
    html = render_analytical_report_html(r)
    assert "Конкурентный анализ" in html
    assert "Мировой рынок" in html
    assert "судебные" in html.lower() or "производства" in html.lower()


def test_extract_companies_from_evidence():
    ev = [{
        "title": "Market",
        "quote": "Linde plc и Air Liquide занимают рынок электронных газов",
    }]
    names = extract_company_names_from_evidence(ev)
    assert any("Linde" in n for n in names) or any("Air" in n for n in names)


def test_report_includes_directions_and_relation_classes():
    """Stage A/C: directions with roles and Stage B relation classes persist in the report."""
    from osint_agent.market.analytical_report import build_analytical_report

    summary = {
        "company_name": "ООО ГИДРОЭЛ",
        "legal_entity_inn": "5040133380",
        "company_research": {
            "official_site": "https://hydroel-shop.ru/",
            "site_status": "verified",
            "directions": [{
                "direction_id": "d1",
                "product_category_ru": "Гидравлические блоки",
                "role": "manufacturer",
                "status": "supported",
                "evidence": [{"quote": "Проектируем и изготавливаем гидроблоки"}],
            }],
            "limitations": ["Лимит HTML-страниц"],
        },
        "product_scope": {
            "directions": [{
                "direction_id": "d1",
                "product_category_ru": "Гидравлические блоки",
                "role": "manufacturer",
            }],
            "product": "Гидравлические блоки",
            "official_site": "https://hydroel-shop.ru/",
            "site_status": "verified",
        },
        "competitor_research": {
            "candidates_table": [
                {"name": "Sun Hydraulics", "relation_class": "direct_competitor",
                 "direction_id": "d1", "territory": "russia", "product": "Гидроблоки",
                 "reason": "Пересечение покупателей", "links": ["https://sunhydraulics.ru/"],
                 "evidence": [{"quote": "Производство гидроблоков", "url": "https://sunhydraulics.ru/"}]},
                {"name": "Walvoil", "relation_class": "supplier_partner",
                 "direction_id": "d1", "territory": "world", "product": "Клапаны",
                 "reason": "Поставщик", "links": [], "evidence": []},
                {"name": "Мусор", "relation_class": "rejected",
                 "direction_id": "d1", "territory": "russia", "product": "",
                 "reason": "product_overlap_not_shown", "links": [], "evidence": []},
            ],
            "rejected": [
                {"name": "Мусор", "relation_class": "rejected", "reason": "product_overlap_not_shown",
                 "direction_id": "d1"},
            ],
            "note": "Поставщики отдельно",
        },
        "competitor_relation_table": [
            {"name": "Sun Hydraulics", "relation_class": "direct_competitor",
             "direction_id": "d1", "territory": "russia", "product": "Гидроблоки",
             "reason": "Пересечение покупателей", "links": ["https://sunhydraulics.ru/"],
             "evidence": [{"quote": "Производство гидроблоков", "url": "https://sunhydraulics.ru/"}]},
            {"name": "Walvoil", "relation_class": "supplier_partner",
             "direction_id": "d1", "territory": "world", "product": "Клапаны",
             "reason": "Поставщик", "links": [], "evidence": []},
        ],
        "limitations": ["Источники частично недоступны"],
    }
    report = build_analytical_report(summary, company_name="ООО ГИДРОЭЛ", inn="5040133380")
    assert report["company"]["directions"], "directions stored in report"
    d = report["company"]["directions"][0]
    assert d["role"] == "manufacturer"
    assert d["direction_id"] == "d1"
    assert report["company"]["site_status"] == "verified"
    assert report["competitors"]["russia"], "direct competitor kept"
    assert any(r.get("relation_class") == "direct_competitor" for r in report["competitors"]["russia"])
    assert report["competitors"]["suppliers_partners"], "suppliers separated"
    assert report["competitors"]["suppliers_partners"][0]["name"] == "Walvoil"
    assert not any(r.get("name") == "Мусор" for r in report["competitors"]["russia"])
    assert report["competitors"]["rejected"], "rejected with reasons"
    assert "company_directions" not in report["gaps"] or report["company"]["directions"]
    assert any("Лимит HTML" in x or "Источники" in x for x in report["limitations"])


def test_report_without_directions_lists_gap():
    from osint_agent.market.analytical_report import build_analytical_report
    report = build_analytical_report({"company_name": "X", "legal_entity_inn": "1"}, company_name="X", inn="1")
    assert "company_directions" in report["gaps"]
    assert report["company"]["directions"] == []
