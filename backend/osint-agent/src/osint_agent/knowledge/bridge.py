"""Bridge: market / legal-entity / external evidence → shared knowledge store (Stage E).

Keeps Task1 contracts intact: market modules still return their own summary shape.
This module only persists provenance into the shared PostgreSQL so the three
modules reuse one corpus without losing evidence_id / access / origin.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from osint_agent.knowledge.pg_repository import KnowledgePgRepository


def _now() -> datetime:
    return datetime.now(timezone.utc)


class KnowledgeBridge:
    def __init__(self, repo: KnowledgePgRepository):
        self.repo = repo

    def upsert_company_entity(
        self,
        *,
        name: str,
        inn: str | None = None,
        ogrn: str | None = None,
        workspace_id: str | None = None,
        alt_names: list[str] | None = None,
    ) -> str:
        identifiers: dict[str, Any] = {}
        if inn:
            identifiers["inn"] = {"value": inn, "registry": "fns", "country": "ru"}
        if ogrn:
            identifiers["ogrn"] = {"value": ogrn, "registry": "fns", "country": "ru"}
        return self.repo.upsert_entity(
            "org",
            name,
            identifiers,
            workspace_id=workspace_id,
            alt_names=alt_names,
        )

    def persist_market_evidence(
        self,
        summary: dict[str, Any],
        *,
        workspace_id: str | None = None,
        inn: str | None = None,
    ) -> dict[str, Any]:
        """Store company + external evidence_refs from Task1 auto-analysis summary.

        Does NOT invent facts. Empty/missing stays missing. Snippets remain
        claim_type='unverified_snippet' / verification_status='unreviewed'.
        """
        company = summary.get("company") or {}
        name = company.get("name") or company.get("full_name") or "unknown"
        entity_id = self.upsert_company_entity(
            name=name,
            inn=inn or company.get("inn"),
            workspace_id=workspace_id,
        )

        stored_docs = 0
        stored_ev = 0
        evidence_map: dict[str, str] = {}

        for ref in summary.get("evidence_refs") or summary.get("external_evidence") or []:
            ev_id = self._persist_evidence_ref(ref, entity_id=entity_id, workspace_id=workspace_id)
            if ev_id:
                evidence_map[str(ref.get("id") or "")] = ev_id
                stored_ev += 1
                if ref.get("url") or ref.get("title"):
                    stored_docs += 1

        # typed legal relations → entity_relations (not competitors)
        for rel in summary.get("related_organizations") or summary.get("legal_relations") or []:
            self.repo.add_entity_relation(
                subject_id=entity_id,
                relation=str(rel.get("role") or rel.get("relation") or "related"),
                object_label=rel.get("name"),
                evidence_id=evidence_map.get(str((rel.get("evidence_ids") or [""])[0])),
            )

        return {
            "entity_id": entity_id,
            "documents_touched": stored_docs,
            "evidence_stored": stored_ev,
            "evidence_id_map": evidence_map,
        }

    def _persist_evidence_ref(
        self,
        ref: dict[str, Any],
        *,
        entity_id: str | None,
        workspace_id: str | None,
    ) -> str | None:
        statement = (ref.get("quote") or ref.get("title") or ref.get("statement") or "").strip()
        if not statement:
            return None
        claim_type = ref.get("type") or "unverified_snippet"
        if claim_type in ("web_snippet", "search_snippet"):
            claim_type = "unverified_snippet"
        doc_id = None
        url = ref.get("url")
        title = ref.get("title")
        if url or title:
            origin = ref.get("id") or url or title
            doc_id = self.repo.add_document(
                source_type=str(ref.get("source_id") or "web"),
                url=url,
                title=title,
                origin_id=f"bridge:{origin}",
                metadata={"completeness": ref.get("completeness"), "query": ref.get("query")},
                workspace_id=workspace_id,
            )
        return self.repo.add_evidence(
            statement=statement[:2000],
            claim_type=claim_type,
            document_id=doc_id,
            entity_id=entity_id,
            quote=ref.get("quote"),
            locator=ref.get("locator"),
            workspace_id=workspace_id,
        )

    def persist_llm_claim(
        self,
        claim: dict[str, Any],
        *,
        entity_id: str | None = None,
        workspace_id: str | None = None,
    ) -> str | None:
        """LLM interpretation is claim_type=interpretation, never a source fact (§9)."""
        text = (claim.get("text") or claim.get("statement") or "").strip()
        if not text:
            return None
        return self.repo.add_evidence(
            statement=text[:2000],
            claim_type="interpretation",
            entity_id=entity_id,
            quote=claim.get("quote"),
            workspace_id=workspace_id,
        )

    def bind_research(
        self,
        *,
        legal_entity_inn: str | None = None,
        project_ref: str | None = None,
        product_ref: str | None = None,
        analysis_version_id: str | None = None,
        report_version_id: str | None = None,
        workspace_id: str | None = None,
    ) -> str:
        return self.repo.insert_research_binding(
            project_ref=project_ref,
            legal_entity_inn=legal_entity_inn,
            product_ref=product_ref,
            analysis_version_id=analysis_version_id,
            report_version_id=report_version_id,
            workspace_id=workspace_id,
        )
