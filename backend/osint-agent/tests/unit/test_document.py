"""Tests for Document Connector."""

import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from osint_agent.connectors.document import (
    DocumentConnector,
    DocumentAnalyzer,
    MockDocumentConnector,
)
from osint_agent.models import ConnectorQuery


@pytest.mark.unit
class TestMockDocumentConnector:
    """Tests for MockDocumentConnector."""

    @pytest.fixture
    def connector(self):
        return MockDocumentConnector()

    @pytest.mark.asyncio
    async def test_fetch_pitch_deck(self, connector):
        """Test fetching pitch deck metadata."""
        query = ConnectorQuery(
            query_type="document",
            params={"file_path": "/path/to/pitch_deck.pdf"},
        )

        result = await connector.fetch(query)

        assert result.success is True
        assert result.data["format"] == "PDF"
        assert result.data["author"] == "Иванов Петр Сергеевич"
        assert result.data["pages"] == 15
        assert result.data["is_encrypted"] is False

    @pytest.mark.asyncio
    async def test_fetch_contract(self, connector):
        """Test fetching contract metadata."""
        query = ConnectorQuery(
            query_type="document",
            params={"file_path": "/path/to/contract.docx"},
        )

        result = await connector.fetch(query)

        assert result.success is True
        assert result.data["format"] == "DOCX"
        assert result.data["author"] == "Петров Алексей Викторович"
        assert result.data["title"] == "Договор на оказание услуг"

    @pytest.mark.asyncio
    async def test_fetch_financials(self, connector):
        """Test fetching financials metadata."""
        query = ConnectorQuery(
            query_type="document",
            params={"file_path": "/path/to/financials.xlsx"},
        )

        result = await connector.fetch(query)

        assert result.success is True
        assert result.data["format"] == "XLSX"
        assert result.data["sheets_count"] == 3
        assert "Баланс" in result.data["sheets"]

    @pytest.mark.asyncio
    async def test_fetch_photo(self, connector):
        """Test fetching photo metadata with geolocation."""
        query = ConnectorQuery(
            query_type="document",
            params={"file_path": "/path/to/photo.jpg"},
        )

        result = await connector.fetch(query)

        assert result.success is True
        assert result.data["format"] == "JPEG"
        assert result.data["Make"] == "Apple"
        assert result.data["Model"] == "iPhone 14 Pro"
        assert result.data["geolocation"]["latitude"] == 55.7558
        assert result.data["geolocation"]["longitude"] == 37.6173

    @pytest.mark.asyncio
    async def test_fetch_presentation(self, connector):
        """Test fetching PowerPoint presentation metadata."""
        query = ConnectorQuery(
            query_type="document",
            params={"file_path": "/path/to/presentation.pptx"},
        )

        result = await connector.fetch(query)

        assert result.success is True
        assert result.data["format"] == "PPTX"
        assert result.data["author"] == "Иванов Петр Сергеевич"
        assert result.data["title"] == "MacroMind Analytics — Pitch Deck"
        assert result.data["slides_count"] == 18
        assert result.data["slides_with_text"] == 15
        assert result.data["total_text_length"] == 4500

    @pytest.mark.asyncio
    async def test_fetch_unknown_file(self, connector):
        """Test fetching unknown file."""
        query = ConnectorQuery(
            query_type="document",
            params={"file_path": "/path/to/unknown.txt"},
        )

        result = await connector.fetch(query)

        assert result.success is True
        assert result.data["format"] == "UNKNOWN"

    @pytest.mark.asyncio
    async def test_fetch_without_path(self, connector):
        """Test fetching without file path."""
        query = ConnectorQuery(
            query_type="document",
            params={},
        )

        result = await connector.fetch(query)

        assert result.success is False
        assert "file_path is required" in result.error


@pytest.mark.unit
class TestDocumentAnalyzer:
    """Tests for DocumentAnalyzer."""

    @pytest.fixture
    def analyzer(self):
        return DocumentAnalyzer()

    def test_analyze_geolocation(self, analyzer):
        """Test Red Flag for geolocation in image."""
        metadata = {
            "format": "JPEG",
            "geolocation": {"latitude": 55.7558, "longitude": 37.6173},
        }

        flags = analyzer.analyze(metadata)

        flag_ids = [f.id for f in flags]
        assert "DOC_GEOLOCATION_FOUND" in flag_ids

    def test_analyze_old_software(self, analyzer):
        """Test Red Flag for old software."""
        metadata = {
            "format": "DOCX",
            "creator": "Microsoft Word 2007",
        }

        flags = analyzer.analyze(metadata)

        flag_ids = [f.id for f in flags]
        assert "DOC_OLD_SOFTWARE" in flag_ids

    def test_analyze_suspicious_author(self, analyzer):
        """Test Red Flag for suspicious author name."""
        metadata = {
            "format": "PDF",
            "author": "admin",
        }

        flags = analyzer.analyze(metadata)

        flag_ids = [f.id for f in flags]
        assert "DOC_SUSPICIOUS_AUTHOR" in flag_ids

    def test_analyze_future_date(self, analyzer):
        """Test Red Flag for future creation date."""
        future_date = datetime(2030, 1, 1).isoformat()
        metadata = {
            "format": "PDF",
            "created": future_date,
        }

        flags = analyzer.analyze(metadata)

        flag_ids = [f.id for f in flags]
        assert "DOC_FUTURE_DATE" in flag_ids

    def test_analyze_emails_found(self, analyzer):
        """Test Red Flag for emails found in document."""
        metadata = {
            "format": "PDF",
            "emails_found": ["ivan@example.com", "petr@test.ru"],
        }

        flags = analyzer.analyze(metadata)

        flag_ids = [f.id for f in flags]
        assert "DOC_EMAILS_FOUND" in flag_ids

    def test_analyze_clean_document(self, analyzer):
        """Test no Red Flags for clean document."""
        metadata = {
            "format": "PDF",
            "author": "Иванов Петр Сергеевич",
            "creator": "Microsoft PowerPoint 2019",
            "created": "2024-01-15T10:30:00",
        }

        flags = analyzer.analyze(metadata)

        assert len(flags) == 0

    def test_analyze_multiple_flags(self, analyzer):
        """Test multiple Red Flags."""
        metadata = {
            "format": "JPEG",
            "author": "admin",
            "geolocation": {"latitude": 55.7558, "longitude": 37.6173},
            "emails_found": ["test@example.com"],
        }

        flags = analyzer.analyze(metadata)

        flag_ids = [f.id for f in flags]
        assert "DOC_SUSPICIOUS_AUTHOR" in flag_ids
        assert "DOC_GEOLOCATION_FOUND" in flag_ids
        assert "DOC_EMAILS_FOUND" in flag_ids
        assert len(flags) == 3


@pytest.mark.unit
class TestDocumentConnector:
    """Tests for DocumentConnector with real files."""

    @pytest.fixture
    def connector(self):
        return DocumentConnector()

    @pytest.mark.asyncio
    async def test_fetch_nonexistent_file(self, connector):
        """Test fetching non-existent file."""
        query = ConnectorQuery(
            query_type="document",
            params={"file_path": "/nonexistent/file.pdf"},
        )

        result = await connector.fetch(query)

        assert result.success is False
        # Path validation blocks files outside allowed directories
        assert "outside allowed directories" in result.error or "File not found" in result.error

    @pytest.mark.asyncio
    async def test_fetch_unsupported_format(self, connector, tmp_path):
        """Test fetching unsupported format."""
        # Create a temporary file
        test_file = tmp_path / "test.txt"
        test_file.write_text("test")

        query = ConnectorQuery(
            query_type="document",
            params={"file_path": str(test_file)},
        )

        result = await connector.fetch(query)

        assert result.success is False
        assert "Unsupported format" in result.error

    @pytest.mark.asyncio
    async def test_fetch_real_pdf(self, connector, tmp_path):
        """Test fetching real PDF metadata."""
        # Skip if pdfplumber not available
        pdfplumber = pytest.importorskip("pdfplumber")
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas

        # Create a simple PDF
        pdf_path = tmp_path / "test.pdf"
        c = canvas.Canvas(str(pdf_path), pagesize=letter)
        c.drawString(100, 750, "Hello World")
        c.save()

        query = ConnectorQuery(
            query_type="document",
            params={"file_path": str(pdf_path)},
        )

        result = await connector.fetch(query)

        assert result.success is True
        assert result.data["format"] == "PDF"
        assert result.data["pages"] == 1
