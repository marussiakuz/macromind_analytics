"""Pitch deck analysis: parsing, flags, summary guard, API. No real model or decks are used."""

from __future__ import annotations

import io
import json
import time
from datetime import date

import httpx
import pytest
from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas

from osint_agent.pitchdeck.entities import extract_entities
from osint_agent.pitchdeck.evaluation import GoldFact, score_deck
from osint_agent.pitchdeck.extract import assess_fact, build_fact, is_runaway, postprocess
from osint_agent.pitchdeck.ingest import DeckReadError, read_deck, sniff_kind
from osint_agent.pitchdeck.llm import LocalLLMError, OllamaClient, ensure_local, salvage_truncated
from osint_agent.pitchdeck.models import DeckFact, FactStatus, Metric, Slide, Verdict
from osint_agent.pitchdeck.normalize import parse_value, parse_years, value_in_text
from osint_agent.pitchdeck.red_flags import detect_red_flags
from osint_agent.pitchdeck.repository import PitchDeckRepository
from osint_agent.pitchdeck.summary import build_summary, numbers_grounded, template_summary


def fact(metric, value, unit="млн руб.", period="", status=FactStatus.fact, slide=1, entity="", label="", index=0):
    parsed = parse_value(value, unit)
    return DeckFact(
        id=f"s{slide}-f{index}-{metric.value}-{value}",
        slide=slide,
        metric=metric,
        label=label,
        value_raw=value,
        unit_raw=unit,
        period_raw=period,
        entity=entity,
        status=status,
        amount=parsed.amount,
        amount_high=parsed.amount_high,
        unit_kind=parsed.unit_kind,
        years=parse_years(period),
        needs_review=False,
    )


def rules(flags):
    return {f.rule for f in flags}


class TestNormalize:
    @pytest.mark.parametrize(
        ("value", "unit", "amount", "kind"),
        [
            ("1 030", "млн руб.", 1.03e9, "RUB"),
            ("$84B", "", 84e9, "USD"),
            ("70+", "млн руб", 70e6, "RUB"),
            ("0,8", "млрд ₽", 0.8e9, "RUB"),
            ("-0,2", "%", -0.2, "percent"),
            ("$700 млн", "млрд $", 700e6, "USD"),
        ],
    )
    def test_parse_value(self, value, unit, amount, kind):
        parsed = parse_value(value, unit)
        assert parsed.amount == pytest.approx(amount)
        assert parsed.unit_kind == kind

    def test_range_keeps_both_ends(self):
        parsed = parse_value("10-15", "%")
        assert (parsed.amount, parsed.amount_high) == (10, 15)

    def test_no_number(self):
        assert parse_value("не указано").amount is None

    def test_years(self):
        assert parse_years("2026–2028") == [2026, 2027, 2028]
        assert parse_years("2021 П") == [2021]
        assert parse_years("") == []

    def test_value_in_text_respects_number_boundaries(self):
        assert value_in_text("1 030", "476 | 1 030 | 1 750")
        assert value_in_text("0,8", "SOM 0.8 млрд")
        assert not value_in_text("30", "1 030")
        assert not value_in_text("476", "")


class TestLocalOnly:
    def test_remote_host_is_refused(self):
        with pytest.raises(LocalLLMError) as error:
            ensure_local("https://llm.example.com")
        assert error.value.code == "remote_llm_refused"

    def test_loopback_allowed(self):
        assert ensure_local("http://127.0.0.1:11434/") == "http://127.0.0.1:11434"

    def test_client_refuses_remote_on_construction(self):
        with pytest.raises(LocalLLMError):
            OllamaClient("http://10.0.0.5:11434", "m")


class TestLlmParsing:
    def test_salvage_keeps_complete_items(self):
        cut = '{"facts":[{"value":"1"},{"value":"2"},{"val'
        assert salvage_truncated(cut) == {"facts": [{"value": "1"}, {"value": "2"}]}

    def test_salvage_gives_up_on_garbage(self):
        assert salvage_truncated("not json") is None

    @pytest.mark.asyncio
    async def test_unreachable_ollama_is_a_controlled_error(self):
        def boom(request):
            raise httpx.ConnectError("down")

        client = OllamaClient("http://127.0.0.1:1", "m", transport=httpx.MockTransport(boom))
        with pytest.raises(LocalLLMError) as error:
            await client.health()
        assert error.value.code == "llm_unavailable"
        await client.aclose()


class TestPostprocess:
    def test_market_label_absent_from_slide_becomes_market_size(self):
        item = fact(Metric.market_tam, "100", "млрд руб.")
        assert postprocess([item], "Рынок техобслуживания 100 млрд")[0].metric == Metric.market_size

    def test_market_label_present_is_kept(self):
        item = fact(Metric.market_tam, "100", "млрд руб.")
        assert postprocess([item], "TAM 100 млрд")[0].metric == Metric.market_tam

    def test_percent_market_size_becomes_share(self):
        item = fact(Metric.market_size, "30", "%")
        assert postprocess([item], "30%")[0].metric == Metric.market_share

    def test_repeated_row_collapses_even_with_other_status(self):
        a = fact(Metric.revenue, "5", period="2025", status=FactStatus.fact)
        b = fact(Metric.revenue, "5", period="2025", status=FactStatus.forecast)
        assert len(postprocess([a, b], "5")) == 1

    def test_table_rows_get_entity_from_label(self):
        a = fact(Metric.revenue, "1", period="2025", label="Cyclop")
        b = fact(Metric.revenue, "2", period="2025", label="Smart Engine")
        assert [f.entity for f in postprocess([a, b], "1 2")] == ["Cyclop", "Smart Engine"]

    def test_build_fact_drops_value_without_digits_and_other_metric(self):
        base = {"label": "", "unit": "", "period": "", "entity": "", "status": "fact", "quote": ""}
        assert build_fact({**base, "metric": "revenue", "value": "нет"}, 1, 0, "") is None
        assert build_fact({**base, "metric": "other", "value": "5"}, 1, 0, "") is None

    def test_build_fact_drops_generic_entity_and_repeated_unit(self):
        raw = {"metric": "market_share", "label": "", "value": "25 %", "unit": "%", "period": "2025",
               "entity": "компания", "status": "forecast", "quote": ""}
        built = build_fact(raw, 1, 0, "25 %")
        assert built.entity == "" and built.unit_raw == ""


class TestRedFlags:
    TODAY = date(2026, 10, 30)

    def run(self, facts, slides=None):
        return detect_red_flags(facts, slides or [Slide(number=1, text="x" * 400)], today=self.TODAY)

    def test_hockey_stick(self):
        flags = self.run([
            fact(Metric.revenue, "10", period="2026", status=FactStatus.fact),
            fact(Metric.revenue, "1000", period="2029", status=FactStatus.forecast, slide=2),
        ])
        hit = next(f for f in flags if f.rule == "hockey_stick")
        assert hit.severity.value == "high"
        assert hit.slides == [1, 2]

    def test_modest_growth_is_not_flagged(self):
        flags = self.run([
            fact(Metric.revenue, "100", period="2026"),
            fact(Metric.revenue, "150", period="2029", status=FactStatus.forecast),
        ])
        assert "hockey_stick" not in rules(flags)

    def test_plan_fact_gap(self):
        flags = self.run([
            fact(Metric.revenue, "21,3", period="2025", status=FactStatus.forecast),
            fact(Metric.revenue, "5", period="2025", status=FactStatus.fact),
        ])
        assert "plan_fact_gap" in rules(flags)

    def test_plan_fact_gap_ignores_other_units(self):
        flags = self.run([
            fact(Metric.revenue, "22,9", period="2021", status=FactStatus.forecast),
            fact(Metric.revenue, "63", "%", period="2021", status=FactStatus.fact),
        ])
        assert "plan_fact_gap" not in rules(flags)

    def test_quarter_is_not_compared_with_a_full_year(self):
        quarter = fact(Metric.revenue, "7,9", period="2019", status=FactStatus.fact, label="Выручка за 1 квартал 2019")
        year = fact(Metric.revenue, "246", period="2019", status=FactStatus.forecast, slide=2)
        same_status = fact(Metric.revenue, "246", period="2019", status=FactStatus.fact, slide=2)
        assert "plan_fact_gap" not in rules(self.run([quarter, year]))
        assert "inconsistent_values" not in rules(self.run([quarter, same_status]))

    def test_inconsistent_values_across_slides(self):
        flags = self.run([
            fact(Metric.revenue, "160", period="2026", status=FactStatus.forecast, slide=9),
            fact(Metric.revenue, "97", period="2026", status=FactStatus.forecast, slide=20),
        ])
        hit = next(f for f in flags if f.rule == "inconsistent_values")
        assert hit.slides == [9, 20]

    def test_same_value_on_two_slides_is_fine(self):
        flags = self.run([
            fact(Metric.revenue, "160", period="2026", status=FactStatus.forecast, slide=9),
            fact(Metric.revenue, "160", period="2026", status=FactStatus.forecast, slide=20),
        ])
        assert "inconsistent_values" not in rules(flags)

    def test_market_funnel_order(self):
        flags = self.run([
            fact(Metric.market_tam, "10", "млрд руб."),
            fact(Metric.market_sam, "20", "млрд руб."),
        ])
        assert "market_funnel_order" in rules(flags)

    def test_funnel_ignores_different_currencies(self):
        flags = self.run([
            fact(Metric.market_tam, "10", "млрд $"),
            fact(Metric.market_sam, "20", "млрд руб."),
        ])
        assert "market_funnel_order" not in rules(flags)

    def test_revenue_above_market(self):
        flags = self.run([
            fact(Metric.market_som, "1", "млрд руб."),
            fact(Metric.revenue, "2", "млрд руб.", period="2028", status=FactStatus.forecast),
        ])
        assert "revenue_exceeds_market" in rules(flags)

    def test_net_profit_above_ebitda(self):
        flags = self.run([
            fact(Metric.ebitda, "10", period="2026"),
            fact(Metric.net_profit, "20", period="2026"),
        ])
        assert "net_above_ebitda" in rules(flags)

    def test_market_without_source(self):
        flags = self.run([fact(Metric.market_size, "5", "млрд руб.")], [Slide(number=1, text="Рынок 5 млрд" + " x" * 200)])
        assert "market_without_source" in rules(flags)
        sourced = self.run([fact(Metric.market_size, "5", "млрд руб.")], [Slide(number=1, text="Рынок 5 млрд. Источник: RPI" + " x" * 200)])
        assert "market_without_source" not in rules(sourced)

    def test_no_competitors_claim_quotes_the_slide(self):
        flags = self.run([], [Slide(number=4, text="Прямых аналогов нет на российском рынке" + " x" * 200)])
        hit = next(f for f in flags if f.rule == "no_competitors_claim")
        assert hit.slides == [4] and "аналогов нет" in hit.detail

    def test_period_conflict_needs_finance_context(self):
        finance = Slide(number=1, text="Суммарно 2026-2028. Выручка за период 2025-2027" + " x" * 200)
        roadmap = Slide(number=2, text="Этап 1: 2026-2028. Этап 2: 2025-2027" + " x" * 200)
        assert "period_conflict" in rules(self.run([], [finance]))
        assert "period_conflict" not in rules(self.run([], [roadmap]))

    def test_forecast_for_past_years_and_stale_deck(self):
        flags = self.run([fact(Metric.revenue, "5", period="2021", status=FactStatus.forecast)])
        assert {"forecast_in_past", "stale_deck"} <= rules(flags)

    def test_scan_gets_coverage_flag_not_missing_sections(self):
        flags = self.run([], [Slide(number=1, text="")])
        assert "no_text_layer" in rules(flags) and "missing_sections" not in rules(flags)

    def test_unreviewed_facts_do_not_raise_numeric_flags(self):
        low = fact(Metric.market_tam, "10", "млрд руб.")
        high = fact(Metric.market_sam, "20", "млрд руб.")
        low.needs_review = high.needs_review = True
        assert "market_funnel_order" not in rules(self.run([low, high]))

    def test_high_severity_goes_first(self):
        flags = self.run([
            fact(Metric.market_tam, "10", "млрд руб."),
            fact(Metric.market_sam, "20", "млрд руб."),
        ])
        order = {"high": 0, "medium": 1, "low": 2}
        ranks = [order[f.severity.value] for f in flags]
        assert ranks == sorted(ranks)


class TestSummaryGuard:
    def test_numbers_must_come_from_sources(self):
        assert numbers_grounded("Выручка 1 030 млн", ["выручка: 1 030 млн руб."])
        assert not numbers_grounded("Выручка 2 000 млн", ["выручка: 1 030 млн руб."])

    def test_template_says_when_nothing_is_reliable(self):
        assert "ручной" in template_summary([], []).text

    @pytest.mark.asyncio
    async def test_invented_number_falls_back_to_template(self):
        def reply(request):
            return httpx.Response(200, json={"message": {"content": json.dumps({"summary": "Выручка 999 млн."})}})

        client = OllamaClient("http://127.0.0.1:1", "m", transport=httpx.MockTransport(reply))
        result = await build_summary(client, [Slide(number=1, text="Компания")], [fact(Metric.revenue, "5", period="2025")], [])
        await client.aclose()
        assert result.generated_by == "template" and "отброшена" in result.note
        assert "999" not in result.text

    @pytest.mark.asyncio
    async def test_grounded_summary_is_kept(self):
        def reply(request):
            return httpx.Response(200, json={"message": {"content": json.dumps({"summary": "Заявлена выручка 5 млн."})}})

        client = OllamaClient("http://127.0.0.1:1", "m", transport=httpx.MockTransport(reply))
        result = await build_summary(client, [Slide(number=1, text="Компания")], [fact(Metric.revenue, "5", period="2025")], [])
        await client.aclose()
        assert result.generated_by == "llm"


class TestTrust:
    TEXT = "Выручка 147 млн в 2019 году, подробности на слайде и в приложении"

    def test_number_in_text_layer_is_trusted(self):
        item = fact(Metric.revenue, "147", period="2019")
        item.value_in_text = True
        assess_fact(item, self.TEXT)
        assert item.needs_review is False

    def test_number_missing_from_text_layer_needs_review_even_if_model_agrees(self):
        item = fact(Metric.revenue, "999", period="2019")
        item.value_in_text = False
        item.verdict = Verdict.correct
        assess_fact(item, self.TEXT)
        assert item.needs_review is True

    def test_scan_relies_on_model_check(self):
        item = fact(Metric.revenue, "147", period="2019")
        item.verdict = Verdict.correct
        assess_fact(item, "")
        assert item.needs_review is False
        item.verdict = Verdict.unsure
        assess_fact(item, "")
        assert item.needs_review is True

    def test_long_invented_list_is_runaway(self):
        invented = [fact(Metric.revenue, str(1000 + i), period="2020") for i in range(12)]
        for item in invented:
            item.value_in_text = False
        assert is_runaway(invented, self.TEXT)

    def test_long_grounded_table_is_not_runaway(self):
        table = [fact(Metric.revenue, str(1000 + i), period="2020") for i in range(12)]
        for item in table:
            item.value_in_text = True
        assert not is_runaway(table, self.TEXT)

    def test_scan_with_distinct_values_is_not_runaway(self):
        assert not is_runaway([fact(Metric.revenue, str(i)) for i in range(12)], "")

    def test_repeated_value_loop_is_runaway_without_text_layer(self):
        loop = [fact(Metric.revenue, "1 030", period=str(2000 + i)) for i in range(12)]
        assert is_runaway(loop, "")


class TestEvaluation:
    def gold(self, **kwargs):
        base = {"slide": 1, "metric": "revenue", "value": "5", "unit": "млн руб.", "period": "2025", "status": "fact"}
        return GoldFact.from_dict({**base, **kwargs})

    def pred(self, **kwargs):
        base = {"slide": 1, "metric": "revenue", "amount": 5e6, "years": [2025], "status": "fact", "entity": ""}
        return {**base, **kwargs}

    def test_strict_needs_period_and_status(self):
        gold = [self.gold()]
        assert score_deck(gold, [self.pred(status="forecast")], strict=True)[0].tp == 0
        assert score_deck(gold, [self.pred(status="forecast")], strict=False)[0].tp == 1
        assert score_deck(gold, [self.pred(years=[2024])], strict=True)[0].tp == 0

    def test_any_status_accepts_every_status(self):
        assert score_deck([self.gold(status="any")], [self.pred(status="forecast")], strict=True)[0].tp == 1

    def test_one_prediction_cannot_match_twice(self):
        score, _ = score_deck([self.gold(), self.gold()], [self.pred()], strict=True)
        assert (score.tp, score.fn) == (1, 1)

    def test_f1_formula(self):
        score, _ = score_deck([self.gold(), self.gold(value="6")], [self.pred(), self.pred(amount=9e6)], strict=True)
        assert (score.tp, score.fp, score.fn) == (1, 1, 1)
        assert score.f1 == pytest.approx(0.5)

    def test_entity_alternatives_and_lookalike_letters(self):
        gold = [self.gold(entity="max|сценарий 1")]
        assert score_deck(gold, [self.pred(entity="Сценарий 1 (МАХ)")], strict=True)[0].tp == 1
        assert score_deck(gold, [self.pred(entity="Сценарий 2")], strict=True)[0].tp == 0


class TestEntities:
    def test_names_and_valid_identifiers(self):
        slides = [Slide(number=2, text="ООО «Ромашка», ИНН 7707083893, ОГРН 1027700132195. CEO Иван Петров. Код 1234567890.")]
        found = {(e.kind, e.text) for e in extract_entities(slides)}
        assert ("inn", "7707083893") in found and ("ogrn", "1027700132195") in found
        assert ("person", "Иван Петров") in found
        assert ("inn", "1234567890") not in found

    def test_scan_gives_nothing(self):
        assert extract_entities([Slide(number=1, text="")]) == []


def make_pdf(pages=2) -> bytes:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    for index in range(pages):
        pdf.drawString(100, 700, f"TAM 40 mlrd rub, page {index + 1}, Revenue 2026")
        pdf.showPage()
    pdf.save()
    return buffer.getvalue()


class TestIngest:
    def test_pdf_has_text_and_image(self, tmp_path):
        path = tmp_path / "d.pdf"
        path.write_bytes(make_pdf())
        slides = read_deck(path)
        assert len(slides) == 2
        assert "TAM" in slides[0].text
        assert slides[0].image_png.startswith(b"\x89PNG")

    def test_broken_pdf(self, tmp_path):
        path = tmp_path / "d.pdf"
        path.write_bytes(b"%PDF-broken")
        with pytest.raises(DeckReadError):
            read_deck(path)

    def test_sniff(self):
        assert sniff_kind(b"%PDF-1.7") == ".pdf"
        assert sniff_kind(b"PK\x03\x04") == ".pptx"
        assert sniff_kind(b"MZ") is None


def _ollama(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/api/tags":
        return httpx.Response(200, json={"models": [{"name": "m"}]})
    prompt = json.loads(request.content)["messages"][0]["content"]
    if "извлекаешь" in prompt:
        content = {"facts": [{"metric": "market_tam", "label": "TAM", "value": "40", "unit": "млрд руб.", "period": "",
                              "entity": "", "status": "unknown", "quote": "TAM"}]}
    elif "Проверь факт" in prompt:
        content = {"verdict": "верно"}
    else:
        content = {"summary": "Компания заявляет TAM 40 млрд."}
    return httpx.Response(200, json={"message": {"content": json.dumps(content)}})


@pytest.fixture
def api(tmp_path, monkeypatch):
    from osint_agent.api import pitchdeck
    from osint_agent.main import app

    monkeypatch.setattr(pitchdeck, "_repository", PitchDeckRepository(tmp_path))
    monkeypatch.setattr(
        pitchdeck,
        "build_client",
        lambda: OllamaClient("http://127.0.0.1:11434", "m", transport=httpx.MockTransport(_ollama)),
    )
    with TestClient(app) as client:
        yield client


def _wait(client, analysis_id):
    for _ in range(100):
        record = client.get(f"/api/v1/pitchdeck/analyses/{analysis_id}").json()
        if record["status"] in {"done", "failed"}:
            return record
        time.sleep(0.05)
    raise AssertionError("analysis did not finish")


class TestApi:
    def test_full_flow_and_delete(self, api, tmp_path):
        files = {"file": ("deck.pdf", make_pdf(), "application/pdf")}
        created = api.post("/api/v1/pitchdeck/analyses", files=files)
        assert created.status_code == 202
        analysis_id = created.json()["id"]
        record = _wait(api, analysis_id)
        assert record["status"] == "done"
        result = record["result"]
        assert result["slide_count"] == 2
        assert result["facts"][0]["metric"] == "market_tam"
        assert result["facts"][0]["verdict"] == "correct"
        assert result["summary"]["generated_by"] == "llm"

        image = api.get(f"/api/v1/pitchdeck/analyses/{analysis_id}/slides/1/image")
        assert image.status_code == 200 and image.headers["content-type"] == "image/png"
        assert api.get(f"/api/v1/pitchdeck/analyses/{analysis_id}/slides/99/image").status_code == 404

        assert api.delete(f"/api/v1/pitchdeck/analyses/{analysis_id}").status_code == 204
        assert api.get(f"/api/v1/pitchdeck/analyses/{analysis_id}").status_code == 404
        assert not (tmp_path / analysis_id).exists()

    def test_rejects_wrong_type(self, api):
        fake = api.post("/api/v1/pitchdeck/analyses", files={"file": ("deck.pdf", b"MZ not a pdf", "application/pdf")})
        assert fake.status_code == 415
        renamed = api.post("/api/v1/pitchdeck/analyses", files={"file": ("deck.txt", make_pdf(), "text/plain")})
        assert renamed.status_code == 415

    def test_rejects_oversized(self, api, monkeypatch):
        from osint_agent.api import pitchdeck

        monkeypatch.setattr(pitchdeck.settings, "pitchdeck_max_upload_mb", 0)
        response = api.post("/api/v1/pitchdeck/analyses", files={"file": ("deck.pdf", make_pdf(), "application/pdf")})
        assert response.status_code == 413

    def test_ollama_down_stores_nothing(self, api, monkeypatch, tmp_path):
        from osint_agent.api import pitchdeck

        def down(request):
            raise httpx.ConnectError("down")

        monkeypatch.setattr(
            pitchdeck, "build_client",
            lambda: OllamaClient("http://127.0.0.1:1", "m", transport=httpx.MockTransport(down)),
        )
        response = api.post("/api/v1/pitchdeck/analyses", files={"file": ("deck.pdf", make_pdf(), "application/pdf")})
        assert response.status_code == 503
        assert response.json()["detail"]["code"] == "llm_unavailable"
        assert api.get("/api/v1/pitchdeck/analyses").json() == []

    def test_broken_deck_ends_as_failed(self, api):
        created = api.post("/api/v1/pitchdeck/analyses", files={"file": ("deck.pdf", b"%PDF-broken", "application/pdf")})
        record = _wait(api, created.json()["id"])
        assert record["status"] == "failed" and record["error_code"] == "unreadable_deck"

    def test_bad_id_is_404(self, api):
        assert api.get("/api/v1/pitchdeck/analyses/../../etc").status_code == 404
        assert api.get("/api/v1/pitchdeck/analyses/not-a-uuid").status_code == 404

    def test_status_reports_missing_model(self, api, monkeypatch):
        from osint_agent.api import pitchdeck

        monkeypatch.setattr(
            pitchdeck, "build_client",
            lambda: OllamaClient("http://127.0.0.1:1", "other", transport=httpx.MockTransport(_ollama)),
        )
        body = api.get("/api/v1/pitchdeck/status").json()
        assert body["available"] is True and body["model_installed"] is False


class TestRepository:
    def test_restart_marks_running_jobs_failed(self, tmp_path):
        repository = PitchDeckRepository(tmp_path)
        analysis_id = repository.create("d.pdf", ".pdf", b"x")
        repository.set_progress(analysis_id, 1, 5)
        assert repository.fail_interrupted() == 1
        assert repository.get(analysis_id)["error_code"] == "interrupted"
