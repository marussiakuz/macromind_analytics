"""Google Scholar Connector — получение данных из Google Scholar.

Источник: https://scholar.google.com

Получает:
- Публикации: title, authors, year, citations, venue
- h-index, i10-index
- Тематика исследований

Ограничения:
- Парсинг HTML (нет официального API)
- Rate limiting: ~1 запрос в 2 секунды (Google блокирует)
"""

import re
from typing import Any
from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from person_osint.connectors.base import BaseConnector
from person_osint.models import ConnectorQuery, ConnectorResult


class GoogleScholarConnector(BaseConnector):
    """Google Scholar — парсинг scholarly.google.com."""

    BASE_URL = "https://scholar.google.com"

    @property
    def name(self) -> str:
        return "scholar"

    @property
    def rate_limit(self) -> int:
        return 30  # ~1 request per 2 seconds

    async def fetch(self, query: ConnectorQuery) -> ConnectorResult:
        """Получить данные из Google Scholar.

        Args:
            query: ConnectorQuery с params:
                - full_name: str (имя автора)
                - или author_id: str (ID автора в Scholar)

        Returns:
            ConnectorResult с публикациями
        """
        full_name = query.params.get("full_name")
        author_id = query.params.get("author_id")

        try:
            if author_id:
                result = await self._get_author_profile(author_id)
            elif full_name:
                result = await self._search_author(full_name)
            else:
                return ConnectorResult(
                    success=False,
                    source=self.name,
                    error="full_name or author_id is required",
                )

            return ConnectorResult(
                success=True,
                data=result,
                source=self.name,
                confidence=0.8,
            )

        except Exception as e:
            return ConnectorResult(
                success=False,
                source=self.name,
                error=str(e),
            )

    async def _search_author(self, full_name: str) -> dict[str, Any]:
        """Поиск автора по имени."""
        client = await self.get_client()

        search_url = f"{self.BASE_URL}/scholar?q=author:{quote_plus(full_name)}"
        response = await client.get(search_url)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "lxml")

        # Найти ссылку на профиль автора
        author_link = soup.select_one("a.gs_ai_name")
        if not author_link:
            return {"found": False, "message": "No author found"}

        href = author_link.get("href", "")
        author_id_match = re.search(r"user=([^&]+)", href)
        if not author_id_match:
            return {"found": False, "message": "Could not extract author ID"}

        author_id = author_id_match.group(1)
        return await self._get_author_profile(author_id)

    async def _get_author_profile(self, author_id: str) -> dict[str, Any]:
        """Получить профиль автора по ID."""
        client = await self.get_client()

        url = f"{self.BASE_URL}/citations?user={author_id}&hl=en"
        response = await client.get(url)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "lxml")

        profile: dict[str, Any] = {
            "found": True,
            "author_id": author_id,
            "profile_url": url,
            "source": "scholar",
        }

        # Имя
        name_el = soup.select_one("#gsc_prf_in")
        if name_el:
            profile["full_name"] = name_el.get_text(strip=True)

        # Аффилиация
        aff_el = soup.select_one(".gsc_prf_il")
        if aff_el:
            profile["affiliation"] = aff_el.get_text(strip=True)

        # Области исследований
        interests = [i.get_text(strip=True) for i in soup.select("#gsc_prf_int a")]
        profile["interests"] = interests

        # Статистика цитирований
        stats_cells = soup.select("td.gsc_rsb_std")
        if len(stats_cells) >= 6:
            try:
                profile["citations_all"] = int(stats_cells[0].get_text(strip=True))
                profile["citations_since_2019"] = int(stats_cells[1].get_text(strip=True))
                profile["h_index_all"] = int(stats_cells[2].get_text(strip=True))
                profile["h_index_since_2019"] = int(stats_cells[3].get_text(strip=True))
                profile["i10_index_all"] = int(stats_cells[4].get_text(strip=True))
                profile["i10_index_since_2019"] = int(stats_cells[5].get_text(strip=True))
            except (ValueError, IndexError):
                pass

        # Публикации
        publications = await self._get_publications(author_id)
        profile["publications"] = publications

        return profile

    async def _get_publications(self, author_id: str) -> list[dict[str, Any]]:
        """Получить публикации автора."""
        client = await self.get_client()

        url = f"{self.BASE_URL}/citations?user={author_id}&hl=en&sortby=pubdate&cstart=0&pagesize=20"
        response = await client.get(url)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "lxml")
        publications = []

        for row in soup.select("tr.gsc_a_tr"):
            title_el = row.select_one("a.gsc_a_at")
            if not title_el:
                continue

            title = title_el.get_text(strip=True)
            pub_url = title_el.get("href", "")
            if pub_url and not pub_url.startswith("http"):
                pub_url = f"{self.BASE_URL}{pub_url}"

            # Авторы и venue
            authors_el = row.select_one("div.gs_gray")
            authors_text = authors_el.get_text(strip=True) if authors_el else ""

            # Citations
            cite_el = row.select_one("a.gsc_a_ac")
            citations = 0
            if cite_el:
                try:
                    citations = int(cite_el.get_text(strip=True))
                except ValueError:
                    pass

            # Год
            year_el = row.select_one("td.gsc_a_y span")
            year = None
            if year_el:
                try:
                    year = int(year_el.get_text(strip=True))
                except ValueError:
                    pass

            publications.append({
                "title": title,
                "url": pub_url,
                "authors": [a.strip() for a in authors_text.split(",") if a.strip()],
                "year": year,
                "citations": citations,
                "venue": "",
                "source": "scholar",
            })

        return publications[:20]

    async def health_check(self) -> bool:
        """Проверка доступности Google Scholar."""
        try:
            client = await self.get_client()
            response = await client.get(self.BASE_URL, timeout=10.0)
            return response.status_code == 200
        except Exception:
            return False


class MockGoogleScholarConnector(BaseConnector):
    """Mock Google Scholar connector для тестирования."""

    MOCK_DATA: dict[str, dict[str, Any]] = {
        "Иванов Иван Иванович": {
            "found": True,
            "author_id": "abc123",
            "full_name": "Ivan Ivanov",
            "affiliation": "Yandex, Moscow",
            "interests": ["Machine Learning", "Natural Language Processing", "Computer Vision"],
            "citations_all": 1250,
            "citations_since_2019": 890,
            "h_index_all": 18,
            "h_index_since_2019": 14,
            "i10_index_all": 25,
            "i10_index_since_2019": 20,
            "profile_url": "https://scholar.google.com/citations?user=abc123",
            "publications": [
                {
                    "title": "Deep Learning for Russian NLP",
                    "url": "https://scholar.google.com/citations?view_op=view_citation&hl=en&user=abc123&citation_for_view=abc123:1",
                    "authors": ["I Ivanov", "P Petrov"],
                    "year": 2023,
                    "citations": 45,
                    "venue": "ACL 2023",
                    "source": "scholar",
                },
                {
                    "title": "Transformer-based Models for Text Classification",
                    "url": "https://scholar.google.com/citations?view_op=view_citation&hl=en&user=abc123&citation_for_view=abc123:2",
                    "authors": ["I Ivanov", "A Sidorov"],
                    "year": 2022,
                    "citations": 78,
                    "venue": "EMNLP 2022",
                    "source": "scholar",
                },
                {
                    "title": "Multimodal Learning with Vision and Language",
                    "url": "https://scholar.google.com/citations?view_op=view_citation&hl=en&user=abc123&citation_for_view=abc123:3",
                    "authors": ["I Ivanov"],
                    "year": 2021,
                    "citations": 120,
                    "venue": "NeurIPS 2021",
                    "source": "scholar",
                },
            ],
            "source": "scholar",
        },
    }

    @property
    def name(self) -> str:
        return "scholar"

    @property
    def rate_limit(self) -> int:
        return 1000

    async def fetch(self, query: ConnectorQuery) -> ConnectorResult:
        """Вернуть mock данные Scholar."""
        import asyncio
        await asyncio.sleep(0.05)

        full_name = query.params.get("full_name")
        if full_name and full_name in self.MOCK_DATA:
            return ConnectorResult(
                success=True,
                data=self.MOCK_DATA[full_name],
                source=f"{self.name}:mock",
            )

        return ConnectorResult(
            success=True,
            data={"found": False, "message": "Author not found"},
            source=f"{self.name}:mock",
        )

    async def health_check(self) -> bool:
        return True
