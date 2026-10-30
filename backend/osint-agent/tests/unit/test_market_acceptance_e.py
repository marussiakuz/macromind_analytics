"""Stage E: F35–F36 and report export consistency (F31)."""

import pytest

from osint_agent.market.auto_analysis import (
    add_llm_interpretation_cached,
    build_auto_analysis,
)
from osint_agent.market.llm_cache import shared_budget
from osint_agent.market.report import render_market_report_html
from osint_agent.market.providers.yandex_llm import LLMResult, YandexStudioLLM


def test_f35_keys_absent_from_report_html():
    html = render_market_report_html(
        study={"id": "s1", "version": 1, "market_scope": {"product": "X"}},
        summary=None,
        limitations=["ограничение"],
    )
    assert "CHECKO_API_KEY" not in html
    assert "Api-Key" not in html
    assert "sk-" not in html
    assert "Рынок и конкурентная среда" in html


def test_f36_finances_unavailable_market_still_after():
    # если финансов нет — анализ рынка всё равно формируется
    out = build_auto_analysis({"inn": "1", "name": "X", "okved_main": "64.19"}, None, {})
    assert out["legal_entity_inn"] == "1"
    assert out["product_scope"]["product_status"] == "needs_clarification"
    assert out["limitations"]
    html = render_market_report_html(study={"id": "s"}, summary=out, limitations=out["limitations"])
    assert "Рынок и конкурентная среда" in html
    assert "Пробелы" in html


@pytest.mark.asyncio
async def test_f31_report_matches_saved_summary():
    shared_budget().paid_calls = 0

    class L(YandexStudioLLM):
        async def complete(self, s, p):
            return LLMResult(text='{"interpretation":[],"summary":"нет выводов","risks":[],"questions":[]}',
                             model="m", ok=True)

        async def aclose(self):
            return None

    summary = build_auto_analysis({"inn": "1"}, None, {})
    out = await add_llm_interpretation_cached(summary, llm=L())
    html = render_market_report_html(
        study={"id": out.get("study_id") or "s", "market_scope": out["market_scope"]},
        summary=out,
        limitations=out["limitations"],
    )
    assert out["product_scope"]["product_status"] == "needs_clarification"
    assert "требуют уточнения" in html or "Продукт" in html
    # числа не выдуманы
    assert "TAM" not in html or "≠" in html or "не является" in html.lower()
