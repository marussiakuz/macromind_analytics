"""HTML report with market section (plan §4.3, §17). First format: printable HTML."""

from __future__ import annotations

from decimal import Decimal
from html import escape
from typing import Any


def _money(value: Any, currency: str = "RUB") -> str:
    if value is None or value == "":
        return "—"
    try:
        n = Decimal(str(value))
    except Exception:
        return escape(str(value))
    abs_n = abs(n)
    if abs_n >= Decimal("1e9"):
        return f"{n / Decimal('1e9'):.2f} млрд {currency}"
    if abs_n >= Decimal("1e6"):
        return f"{n / Decimal('1e6'):.2f} млн {currency}"
    return f"{n} {currency}"


def render_market_report_html(
    *,
    study: dict[str, Any] | None,
    summary: dict[str, Any] | None,
    top_down: dict[str, Any] | None = None,
    bottom_up: dict[str, Any] | None = None,
    triangulation: dict[str, Any] | None = None,
    competitors: list[dict[str, Any]] | None = None,
    observations: list[dict[str, Any]] | None = None,
    limitations: list[str] | None = None,
) -> str:
    """Если данных нет — раздел остаётся с пробелами, без выдуманных чисел (plan §1)."""
    scope = (study or {}).get("market_scope") or (summary or {}).get("market_scope") or {}
    limitations = limitations or (summary or {}).get("limitations") or []
    if not limitations:
        limitations = [
            "Оценка не является инвестиционной рекомендацией.",
            "Полнота данных ограничена указанными источниками и границами рынка.",
        ]
    competitors = competitors or []
    observations = observations or []

    td_val = (top_down or {}).get("value")
    pot_val = ((bottom_up or {}).get("potential") or {}).get("value")
    dem_val = ((bottom_up or {}).get("demand") or {}).get("value")
    tri_status = (triangulation or {}).get("status") or (summary or {}).get("triangulation_status") or "insufficient_data"

    gaps = []
    if not td_val:
        gaps.append("Оценка сверху вниз не рассчитана")
    if not pot_val:
        gaps.append("Оценка снизу вверх не рассчитана")
    if tri_status in ("insufficient_data", "not_comparable"):
        gaps.append("Сопоставление методов не подтверждено")

    parts = [
        "<!DOCTYPE html><html lang='ru'><head><meta charset='utf-8'>",
        "<title>Отчет по стартапу — Рынок и конкурентная среда</title>",
        "<style>",
        "body{font-family:system-ui,sans-serif;color:#222;max-width:900px;margin:2rem auto;padding:0 1rem}",
        "h1,h2,h3{color:#111} table{border-collapse:collapse;width:100%;margin:.5rem 0}",
        "td,th{border:1px solid #ccc;padding:.4rem .6rem;font-size:14px} .muted{color:#666;font-size:13px}",
        ".warn{background:#fff8e6;padding:.75rem;border-radius:8px} .gap{background:#f5f5f5;padding:.75rem;border-radius:8px}",
        "@media print{body{margin:0}}",
        "</style></head><body>",
        "<h1>Отчет по стартапу</h1>",
        f"<p class='muted'>study_id={escape(str((study or {}).get('id') or summary.get('study_id') or '—'))} · "
        f"версия={escape(str((study or {}).get('version') or (summary or {}).get('report_version') or '—'))}</p>",
        "<h2>Рынок и конкурентная среда</h2>",
    ]

    parts.append("<h3>1. Границы исследования</h3><table>")
    parts.append(f"<tr><th>Продукт</th><td>{escape(str(scope.get('product') or '—'))}</td></tr>")
    parts.append(f"<tr><th>Покупатель</th><td>{escape(str(scope.get('buyer') or '—'))}</td></tr>")
    parts.append(f"<tr><th>Показатель</th><td>{escape(str(scope.get('measure_type') or 'revenue'))}</td></tr>")
    parts.append(f"<tr><th>Страны</th><td>{escape(', '.join(scope.get('countries') or []) or '—')}</td></tr>")
    parts.append(f"<tr><th>Период</th><td>{escape(str(scope.get('reference_period') or '—'))}</td></tr>")
    parts.append("</table>")

    parts.append("<h3>2. Краткий вывод и полнота данных</h3>")
    if gaps:
        parts.append("<div class='gap'><strong>Пробелы:</strong><ul>")
        for g in gaps:
            parts.append(f"<li>{escape(g)}</li>")
        parts.append("</ul></div>")
    else:
        parts.append("<p>Базовые расчёты заполнены. Проверьте основания и ограничения.</p>")

    parts.append("<h3>3. Оценка сверху вниз (РФ)</h3>")
    parts.append(f"<p><strong>{escape(_money(td_val, (top_down or {}).get('currency', 'RUB')))}</strong></p>")
    if top_down:
        parts.append(f"<p class='muted'>формула: {escape(str(top_down.get('formula') or ''))}</p>")
        for line in (top_down.get("log") or [])[:8]:
            parts.append(f"<div class='muted'>{escape(str(line))}</div>")
    else:
        parts.append("<p class='muted'>Расчёт не выполнялся.</p>")

    parts.append("<h3>4. Оценка снизу вверх</h3>")
    parts.append(
        f"<p>Потенциал: <strong>{escape(_money(pot_val))}</strong> · "
        f"Спрос: <strong>{escape(_money(dem_val))}</strong></p>"
    )
    if not pot_val:
        parts.append("<p class='muted'>Расчёт не выполнялся. Потенциал и спрос — разные показатели.</p>")

    parts.append("<h3>5. Сопоставление методов</h3>")
    parts.append(f"<p>Статус: <strong>{escape(str(tri_status))}</strong>")
    if triangulation and triangulation.get("divergence") is not None:
        parts.append(f" · D = {escape(str(triangulation.get('divergence')))}")
    parts.append("</p>")

    parts.append("<h3>6. Наблюдения и источники</h3>")
    if observations:
        parts.append("<table><tr><th>Показатель</th><th>Значение</th><th>Источник</th><th>Статус</th></tr>")
        for o in observations:
            parts.append(
                f"<tr><td>{escape(str(o.get('metric')))}</td>"
                f"<td>{escape(str(o.get('value') or '—'))} {escape(str(o.get('unit') or ''))}</td>"
                f"<td>{escape(str(o.get('source_id')))}</td>"
                f"<td>{escape(str(o.get('status')))}</td></tr>"
            )
        parts.append("</table>")
    else:
        parts.append("<p class='muted'>Наблюдения не добавлены. Числа не подставлены.</p>")

    parts.append("<h3>7. Конкуренты</h3>")
    if competitors:
        parts.append("<table><tr><th>Компания</th><th>Продукт</th><th>Основание</th></tr>")
        for c in competitors:
            parts.append(
                f"<tr><td>{escape(str(c.get('company_name')))}</td>"
                f"<td>{escape(str(c.get('product_name')))}</td>"
                f"<td>{escape(str(c.get('inclusion_reason') or '—'))}</td></tr>"
            )
        parts.append("</table>")
    else:
        parts.append("<p class='muted'>Конкуренты не добавлены. Раздел сохранён с оговоркой о неполноте.</p>")

    parts.append("<h3>8. Ограничения</h3><div class='warn'><ul>")
    for lim in limitations:
        parts.append(f"<li>{escape(str(lim))}</li>")
    parts.append("</ul></div>")

    parts.append(
        "<p class='muted'>Сформировано без выдуманных значений. "
        "Неизвестное не заменено нулем. Отчет не является инвестиционной рекомендацией.</p>"
    )
    parts.append("</body></html>")
    return "".join(parts)
