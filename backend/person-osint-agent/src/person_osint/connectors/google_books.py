"""Google Books Connector — получение данных из Google Books API.

Источник: https://www.googleapis.com/books/v1

Получает:
- Книги по автору
- ISBN, издательство, год

Ограничения:
- Free API: 1000 requests/day
- Без API ключа (limited)
"""

from typing import Any
from urllib.parse import quote_plus

from person_osint.connectors.base import BaseConnector
from person_osint.models import ConnectorQuery, ConnectorResult


class GoogleBooksConnector(BaseConnector):
    """Google Books API."""

    BASE_URL = "https://www.googleapis.com/books/v1"

    @property
    def name(self) -> str:
        return "books"

    @property
    def rate_limit(self) -> int:
        return 60

    async def fetch(self, query: ConnectorQuery) -> ConnectorResult:
        """Получить книги по автору.

        Args:
            query: ConnectorQuery с params:
                - author: str (имя автора)
                - или title: str (название книги)

        Returns:
            ConnectorResult со списком книг
        """
        author = query.params.get("author")
        title = query.params.get("title")

        try:
            if author:
                result = await self._search_by_author(author)
            elif title:
                result = await self._search_by_title(title)
            else:
                return ConnectorResult(
                    success=False,
                    source=self.name,
                    error="author or title is required",
                )

            return ConnectorResult(
                success=True,
                data=result,
                source=self.name,
                confidence=0.9,
            )

        except Exception as e:
            return ConnectorResult(
                success=False,
                source=self.name,
                error=str(e),
            )

    async def _search_by_author(self, author: str) -> dict[str, Any]:
        """Поиск книг по автору."""
        client = await self.get_client()

        response = await client.get(
            f"{self.BASE_URL}/volumes",
            params={"q": f"inauthor:{author}", "maxResults": 20},
        )
        response.raise_for_status()

        data = response.json()
        items = data.get("items", [])

        books = []
        for item in items:
            volume_info = item.get("volumeInfo", {})
            books.append(self._normalize_book(volume_info))

        return {
            "found": len(books) > 0,
            "author": author,
            "total_items": data.get("totalItems", 0),
            "books": books,
            "source": "google_books",
        }

    async def _search_by_title(self, title: str) -> dict[str, Any]:
        """Поиск книги по названию."""
        client = await self.get_client()

        response = await client.get(
            f"{self.BASE_URL}/volumes",
            params={"q": title, "maxResults": 5},
        )
        response.raise_for_status()

        data = response.json()
        items = data.get("items", [])

        if not items:
            return {"found": False, "message": "Book not found"}

        book = self._normalize_book(items[0].get("volumeInfo", {}))
        return {"found": True, "book": book, "source": "google_books"}

    def _normalize_book(self, volume_info: dict[str, Any]) -> dict[str, Any]:
        """Нормализовать данные книги."""
        return {
            "title": volume_info.get("title", ""),
            "authors": volume_info.get("authors", []),
            "year": self._extract_year(volume_info.get("publishedDate")),
            "publisher": volume_info.get("publisher"),
            "isbn": self._extract_isbn(volume_info.get("industryIdentifiers", [])),
            "description": volume_info.get("description"),
            "page_count": volume_info.get("pageCount"),
            "categories": volume_info.get("categories", []),
            "average_rating": volume_info.get("averageRating"),
            "ratings_count": volume_info.get("ratingsCount"),
            "thumbnail": volume_info.get("imageLinks", {}).get("thumbnail"),
            "preview_link": volume_info.get("previewLink"),
            "source": "google_books",
        }

    def _extract_year(self, date_str: str | None) -> int | None:
        """Извлечь год из строки даты."""
        if not date_str:
            return None
        try:
            return int(date_str[:4])
        except (ValueError, IndexError):
            return None

    def _extract_isbn(self, identifiers: list[dict]) -> str | None:
        """Извлечь ISBN."""
        for ident in identifiers:
            if ident.get("type") == "ISBN_13":
                return ident.get("identifier")
            if ident.get("type") == "ISBN_10":
                return ident.get("identifier")
        return None

    async def health_check(self) -> bool:
        """Проверка доступности Google Books API."""
        try:
            client = await self.get_client()
            response = await client.get(
                f"{self.BASE_URL}/volumes?q=test&maxResults=1",
                timeout=10.0,
            )
            return response.status_code == 200
        except Exception:
            return False


class MockGoogleBooksConnector(BaseConnector):
    """Mock Google Books connector для тестирования."""

    MOCK_DATA: dict[str, dict[str, Any]] = {
        "Иванов Иван Иванович": {
            "found": True,
            "author": "Иванов Иван Иванович",
            "total_items": 2,
            "books": [
                {
                    "title": "Машинное обучение: практическое руководство",
                    "authors": ["Иванов И.И."],
                    "year": 2022,
                    "publisher": "Питер",
                    "isbn": "978-5-4461-1234-5",
                    "description": "Полное руководство по ML для практиков",
                    "page_count": 450,
                    "categories": ["Computers"],
                    "average_rating": 4.5,
                    "ratings_count": 120,
                    "source": "google_books",
                },
                {
                    "title": "Python для анализа данных",
                    "authors": ["Иванов И.И.", "Петров П.П."],
                    "year": 2020,
                    "publisher": "Диалектика",
                    "isbn": "978-5-907123-45-6",
                    "description": "Пандас, NumPy, Scikit-learn",
                    "page_count": 380,
                    "categories": ["Computers"],
                    "average_rating": 4.2,
                    "ratings_count": 85,
                    "source": "google_books",
                },
            ],
            "source": "google_books",
        },
    }

    @property
    def name(self) -> str:
        return "books"

    @property
    def rate_limit(self) -> int:
        return 1000

    async def fetch(self, query: ConnectorQuery) -> ConnectorResult:
        """Вернуть mock данные Books."""
        import asyncio
        await asyncio.sleep(0.05)

        author = query.params.get("author")
        if author and author in self.MOCK_DATA:
            return ConnectorResult(
                success=True,
                data=self.MOCK_DATA[author],
                source=f"{self.name}:mock",
            )

        return ConnectorResult(
            success=True,
            data={"found": False, "message": "No books found"},
            source=f"{self.name}:mock",
        )

    async def health_check(self) -> bool:
        return True
