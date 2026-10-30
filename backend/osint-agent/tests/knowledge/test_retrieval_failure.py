"""Loss of the embedding HTTP service must preserve available text results."""
from unittest.mock import Mock

import httpx

from osint_agent.knowledge.retrieval import EvidenceRetriever


def test_hybrid_keeps_keyword_evidence_when_embedding_connection_fails():
    repo = Mock()
    repo.search_text.return_value = []
    repo.search_chunks_text.return_value = [
        {"chunk_id": "c1", "document_id": "d1", "text": "RPA market evidence"}
    ]
    repo.save_retrieval_run.return_value = "r1"

    def unavailable(question):
        raise httpx.ConnectError("service offline")

    result = EvidenceRetriever(repo, embed_fn=unavailable).retrieve("RPA", workspace_id="ws")
    assert result.items[0].document_id == "d1"
    assert "embedding_service_unavailable" in result.limitations
    repo.vector_search.assert_not_called()
