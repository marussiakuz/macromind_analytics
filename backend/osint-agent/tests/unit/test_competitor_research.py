"""Stage B: direction queries, relation classes, supplier protection."""

from __future__ import annotations

from osint_agent.market.competitor_research import (
    classify_candidate,
    detect_product_overlap,
    direction_search_queries,
    extract_candidate_names,
    normalize_company_key,
    rank_candidates,
    suppliers_from_directions,
    truncate_portfolio,
)

DIR = {
    "direction_id": "d1",
    "product_category_ru": "Гидравлические блоки клапанов",
    "product_category_en": "Hydraulic manifold blocks",
    "role": "manufacturer",
    "applications": ["Сельскохозяйственная техника", "Дорожно-строительная техника"],
    "buyer_segments": ["Производители техники"],
    "geography": "Россия",
    "brands": [
        {"name": "Hydroel", "relation": "own_brand"},
        {"name": "Walvoil", "relation": "supplier"},
        {"name": "Sofima", "relation": "resale"},
    ],
}

OWN = ["ООО «ГИДРОЭЛ ИНЖИНИРИНГ»", "ГидроЭл"]
SUPPLIERS = suppliers_from_directions([DIR])


class TestNormalizeKey:
    def test_strips_legal_suffix(self):
        assert normalize_company_key("ООО «Ромашка»") == normalize_company_key("Ромашка")
        assert normalize_company_key("JSE Group LLC") == normalize_company_key("JSE Group")


class TestDirectionQueries:
    def test_includes_category_application_territory(self):
        qs = direction_search_queries(DIR, lang="ru")
        assert qs
        joined = " ".join(qs)
        assert "Гидравлические блоки" in joined
        assert "производители" in joined.lower()
        assert "Россия" in joined

    def test_en_fallback(self):
        qs = direction_search_queries(
            {"product_category_en": "Hydraulic hoses", "role": "manufacturer"}, lang="en",
        )
        assert any("manufacturer" in q.lower() for q in qs)


class TestSupplierProtection:
    def test_suppliers_from_directions(self):
        assert "Walvoil" in SUPPLIERS
        assert "Sofima" in SUPPLIERS
        assert "Hydroel" not in SUPPLIERS

    def test_supplier_is_not_direct_competitor(self):
        row = classify_candidate(
            name="Walvoil",
            direction=DIR,
            own_company_names=OWN,
            supplier_or_partner_names=SUPPLIERS,
            quotes=["Дистрибьютор Walvoil на территории России. Продажа клапанов."],
            territory="world",
            territory_confirmed=None,
            buyers_overlap=True,
            role_compatible=True,
            product_overlap=True,
        )
        assert row["relation_class"] == "supplier_partner"
        assert row["relation_class"] != "direct_competitor"

    def test_supplier_claim_without_list_is_not_relation(self):
        # Astra P1: self-description "we are a distributor" ≠ relation to the studied firm.
        row = classify_candidate(
            name="ООО Ромашка",
            direction=DIR,
            own_company_names=OWN,
            supplier_or_partner_names=[],
            quotes=["Уполномоченный дистрибьютор и поставщик оборудования."],
            territory="world",
            territory_confirmed=None,
            buyers_overlap=False,
            role_compatible=True,
            product_overlap=True,
        )
        assert row["relation_class"] != "supplier_partner"


class TestForeignAnalog:
    def test_foreign_analog_is_not_direct_competitor(self):
        row = classify_candidate(
            name="Parker Hannifin",
            direction=DIR,
            own_company_names=OWN,
            supplier_or_partner_names=SUPPLIERS,
            quotes=["Parker Hannifin manufactures hydraulic manifolds for mobile equipment."],
            territory="world",
            territory_confirmed=False,
            buyers_overlap=True,
            role_compatible=True,
            product_overlap=True,
        )
        assert row["relation_class"] == "product_analog"
        assert row["territory_status"] == "unknown"
        assert "не прям" in row["reason"].lower() or "аналог" in row["reason"].lower()


class TestDirectCompetitor:
    def test_russia_confirmed_with_buyers_and_role(self):
        row = classify_candidate(
            name="АВА Гидросистемы",
            direction=DIR,
            own_company_names=OWN,
            supplier_or_partner_names=SUPPLIERS,
            quotes=[
                "АВА Гидросистемы производит гидравлические блоки клапанов для сельскохозяйственной "
                "техники. Поставки по России. Производитель гидроблоков."
            ],
            territory="russia",
            territory_confirmed=True,
            buyers_overlap=True,
            role_compatible=True,
            product_overlap=True,
        )
        assert row["relation_class"] == "direct_competitor"

    def test_self_company_rejected(self):
        row = classify_candidate(
            name="ГидроЭл Инжиниринг",
            direction=DIR,
            own_company_names=OWN,
            supplier_or_partner_names=SUPPLIERS,
            quotes=["ГИДРОЭЛ производит гидроблоки."],
            territory="russia",
            territory_confirmed=True,
            buyers_overlap=True,
            role_compatible=True,
            product_overlap=True,
        )
        assert row["relation_class"] == "rejected"
        assert row["reason"] == "self_company"

    def test_no_product_overlap_rejected(self):
        row = classify_candidate(
            name="Трактор",
            direction=DIR,
            own_company_names=OWN,
            supplier_or_partner_names=SUPPLIERS,
            quotes=["Производим сельскохозяйственную технику."],
            territory="russia",
            territory_confirmed=True,
            buyers_overlap=True,
            role_compatible=True,
            product_overlap=False,
        )
        assert row["relation_class"] == "rejected"
        assert row["reason"] == "product_overlap_not_shown"


class TestNamingRules:
    def test_generic_product_is_not_duplicate_identity(self):
        # Two industrial firms with same generic product line are different companies.
        a = normalize_company_key("ООО Северная Гидравлика")
        b = normalize_company_key("ООО Южная Гидравлика")
        assert a != b

    def test_extract_names_from_rows(self):
        names = extract_candidate_names({
            "title": "ООО «АВА Гидросистемы» — производство гидроблоков",
            "quote": "Компания JSE Group поставляет клапаны.",
        })
        assert any("АВА" in n for n in names)

    def test_detect_product_overlap(self):
        assert detect_product_overlap(DIR, ["Производство гидравлических блоков клапанов"])
        assert not detect_product_overlap(DIR, ["Бытовая химия и косметика"])


class TestPortfolioOrder:
    def test_rank_and_cap(self):
        rows = [
            {"name": "A", "relation_class": "candidate_for_check", "territory": "russia",
             "evidence": [], "match": {}, "links": []},
            {"name": "B", "relation_class": "direct_competitor", "territory": "russia",
             "evidence": [{"quote": "x"}], "match": {"applications": True}, "links": ["u"]},
            {"name": "C", "relation_class": "rejected", "territory": "russia",
             "evidence": [], "match": {}, "links": []},
            {"name": "D", "relation_class": "product_analog", "territory": "world",
             "evidence": [{"quote": "y"}], "match": {"applications": True}, "links": ["u"]},
        ]
        ranked = rank_candidates(rows)
        assert ranked[0]["name"] == "B"
        capped = truncate_portfolio(ranked)
        names = [r["name"] for r in capped]
        assert "B" in names and "D" in names
        assert "C" not in names


class TestNameNoiseFilter:
    def test_certificate_codes_rejected(self):
        from osint_agent.market.competitor_research import is_plausible_company_name, extract_candidate_names
        assert not is_plausible_company_name("RU.MP04.B03.369")
        assert not is_plausible_company_name("BC 64011E")
        names = extract_candidate_names({
            "title": "Сертификат соответствия RU.MP04.B03.369",
            "quote": "Качество подтверждено сертификатом RU.MP04.B03.369. См. также 640.11.",
        })
        assert not any("RU.MP" in n for n in names)

    def test_geo_and_directory_phrases_rejected(self):
        from osint_agent.market.competitor_research import is_plausible_company_name, extract_candidate_names
        for bad in ("Russia", "Belarus", "Kazakhstan", "China", "Leading Hose Manufacturers",
                    "Our Latest Price", "Cartridge Valves", "Top Hydraulic System Manufacturers"):
            assert not is_plausible_company_name(bad), bad
        names = extract_candidate_names({
            "title": "Top Hydraulic System Manufacturers",
            "quote": "Russia Belarus Kazakhstan. Compare prices. Metoree profile.",
        })
        assert names == [] or all(not n.lower().startswith("top ") for n in names)

    def test_real_brand_names_accepted(self):
        from osint_agent.market.competitor_research import is_plausible_company_name, extract_candidate_names
        for good in ("Sun Hydraulics", "Parker Hannifin", "ООО «АВА Гидросистемы»",
                     "Hydroel", "Сибирские технологии"):
            assert is_plausible_company_name(good), good
        names = extract_candidate_names({
            "title": "Sun Hydraulics — manufacturer",
            "quote": "Parker Hannifin and Sun Hydraulics produce manifold blocks. "
                     "ООО «АВА Гидросистемы» поставляет клапаны.",
        })
        assert any("Sun" in n for n in names)
        assert any("Parker" in n for n in names)
