"""Primary-source provenance: publisher vs aggregator (MIMO_DISCOVERY §3.2/§3.3).

primary_parsed requires actual content check — not just a fetched URL.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

# Known aggregators / paywalls / ad landings — not publisher originals
AGGREGATOR_HOST_HINTS = (
    "scribd.", "slideshare.", "researchandmarkets.", "reportlinker.",
    "mordorintelligence.", "grandviewresearch.", "fortunebusinessinsights.",
    "marketsandmarkets.", "alliedmarketresearch.", "t.me", "telegram.",
    "facebook.", "vk.com", "zen.yandex.", "dzen.",
)
PUBLISHER_HINTS = (
    "research", "report", "insight", "whitepaper", "press", "media",
    "исследован", "отчет", "доклад", "аналитик",
)
AD_LANDING_HINTS = (
    "buy now", "request sample", "request a sample", "download sample",
    "купить", "заказать отчет", "price from", "связаться с нами",
)


@dataclass
class Provenance:
    url: str
    host: str
    kind: str  # publisher | aggregator | ad_landing | unknown
    primary_parsed: bool
    supports_claim: bool
    reasons: list[str]


def classify_url(url: str, *, title: str = "", snippet: str = "", body: str = "") -> Provenance:
    host = (urlparse(url).hostname or "").removeprefix("www.")
    blob = f"{url} {title} {snippet} {body[:2000]}".lower()
    reasons: list[str] = []

    kind = "unknown"
    if any(h in host or h in url.lower() for h in AGGREGATOR_HOST_HINTS):
        kind = "aggregator"
        reasons.append("aggregator_host")
    elif any(h in blob for h in AD_LANDING_HINTS) and not any(h in blob for h in PUBLISHER_HINTS):
        kind = "ad_landing"
        reasons.append("paid_or_ad_landing")
    elif any(h in host or h in title.lower() for h in PUBLISHER_HINTS):
        kind = "publisher"
        reasons.append("publisher_hint")

    # Content must look like a report body, not just a nav/ad shell
    text_len = len(re.sub(r"\s+", " ", body or "").strip())
    has_report_signals = bool(re.search(
        r"(объем рынка|market size|cagr|исследован|methodology|методик|"
        r"forecast|прогноз|volume of the market|содержание|table of contents)",
        blob,
    ))
    has_numbers = bool(re.search(r"\d+[.,]?\d*\s*(%|млрд|млн|billion|million|%)", blob))

    primary_parsed = False
    supports_claim = False
    if kind == "publisher" and text_len >= 400 and (has_report_signals or has_numbers):
        primary_parsed = True
        reasons.append("publisher_body_parsed")
        if has_report_signals:
            supports_claim = True
            reasons.append("report_signals_present")
    elif kind == "publisher" and text_len >= 400:
        primary_parsed = True
        reasons.append("publisher_body_short_signals")
    elif kind == "aggregator":
        reasons.append("not_publisher_original")
    elif kind == "ad_landing":
        reasons.append("snippet_or_ad_not_document")

    return Provenance(
        url=url,
        host=host,
        kind=kind,
        primary_parsed=primary_parsed,
        supports_claim=supports_claim,
        reasons=reasons,
    )


def provenance_meta(p: Provenance) -> dict:
    return {
        "primary_url_candidate": True,
        "primary_fetched": True,
        "primary_parsed": p.primary_parsed,
        "supports_claim": p.supports_claim,
        "source_kind": p.kind,
        "provenance_reasons": p.reasons,
        "limitation": None if p.supports_claim else "primary_not_verified",
    }
