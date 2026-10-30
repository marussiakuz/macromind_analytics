"""Tests for Google Scholar, Google Books, and Medium connectors."""

import pytest
from person_osint.connectors.google_scholar import MockGoogleScholarConnector
from person_osint.connectors.google_books import MockGoogleBooksConnector
from person_osint.connectors.medium import MockMediumConnector
from person_osint.models import ConnectorQuery


@pytest.fixture
def scholar():
    return MockGoogleScholarConnector()


@pytest.fixture
def books():
    return MockGoogleBooksConnector()


@pytest.fixture
def medium():
    return MockMediumConnector()


@pytest.mark.unit
class TestMockGoogleScholarConnector:
    """Tests for MockGoogleScholarConnector."""

    def test_name(self, scholar):
        assert scholar.name == "scholar"

    @pytest.mark.asyncio
    async def test_fetch_known_author(self, scholar):
        result = await scholar.fetch(
            ConnectorQuery(query_type="scholar", params={"full_name": "Иванов Иван Иванович"})
        )
        assert result.success
        assert result.data["found"] is True
        assert result.data["h_index_all"] == 18
        assert result.data["citations_all"] == 1250
        assert len(result.data["publications"]) == 3

    @pytest.mark.asyncio
    async def test_fetch_unknown_author(self, scholar):
        result = await scholar.fetch(
            ConnectorQuery(query_type="scholar", params={"full_name": "Неизвестный"})
        )
        assert result.success
        assert result.data["found"] is False

    @pytest.mark.asyncio
    async def test_fetch_publications(self, scholar):
        result = await scholar.fetch(
            ConnectorQuery(query_type="scholar", params={"full_name": "Иванов Иван Иванович"})
        )
        pubs = result.data["publications"]
        assert pubs[0]["title"] == "Deep Learning for Russian NLP"
        assert pubs[0]["citations"] == 45
        assert pubs[0]["year"] == 2023


@pytest.mark.unit
class TestMockGoogleBooksConnector:
    """Tests for MockGoogleBooksConnector."""

    def test_name(self, books):
        assert books.name == "books"

    @pytest.mark.asyncio
    async def test_fetch_known_author(self, books):
        result = await books.fetch(
            ConnectorQuery(query_type="books", params={"author": "Иванов Иван Иванович"})
        )
        assert result.success
        assert result.data["found"] is True
        assert len(result.data["books"]) == 2

    @pytest.mark.asyncio
    async def test_fetch_unknown_author(self, books):
        result = await books.fetch(
            ConnectorQuery(query_type="books", params={"author": "Неизвестный"})
        )
        assert result.success
        assert result.data["found"] is False

    @pytest.mark.asyncio
    async def test_fetch_books_data(self, books):
        result = await books.fetch(
            ConnectorQuery(query_type="books", params={"author": "Иванов Иван Иванович"})
        )
        book = result.data["books"][0]
        assert book["title"] == "Машинное обучение: практическое руководство"
        assert book["year"] == 2022
        assert book["isbn"] is not None


@pytest.mark.unit
class TestMockMediumConnector:
    """Tests for MockMediumConnector."""

    def test_name(self, medium):
        assert medium.name == "medium"

    @pytest.mark.asyncio
    async def test_fetch_known_person(self, medium):
        result = await medium.fetch(
            ConnectorQuery(query_type="medium", params={"full_name": "Иванов Иван Иванович"})
        )
        assert result.success
        assert result.data["found"] is True
        assert result.data["followers"] == 1500
        assert len(result.data["articles"]) == 2

    @pytest.mark.asyncio
    async def test_fetch_unknown_person(self, medium):
        result = await medium.fetch(
            ConnectorQuery(query_type="medium", params={"full_name": "Неизвестный"})
        )
        assert result.success
        assert result.data["found"] is False

    @pytest.mark.asyncio
    async def test_fetch_articles(self, medium):
        result = await medium.fetch(
            ConnectorQuery(query_type="medium", params={"full_name": "Иванов Иван Иванович"})
        )
        articles = result.data["articles"]
        assert articles[0]["platform"] == "medium"
        assert articles[0]["read_time_min"] == 8
