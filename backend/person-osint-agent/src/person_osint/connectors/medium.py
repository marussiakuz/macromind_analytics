"""Medium Connector — получение данных из Medium.

Источник: https://medium.com

Получает:
- Профиль автора
- Статьи

Ограничения:
- Парсинг HTML (нет официального API для поиска)
- Rate limiting: ~1 запрос в секунду
"""

import re
from typing import Any
from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from person_osint.connectors.base import BaseConnector
from person_osint.models import ConnectorQuery, ConnectorResult


class MediumConnector(BaseConnector):
    """Medium — парсинг medium.com."""

    BASE_URL = "https://medium.com"

    @property
    def name(self) -> str:
        return "medium"

    @property
    def rate_limit(self) -> int:
        return 60

    async def fetch(self, query: ConnectorQuery) -> ConnectorResult:
        """Получить данные из Medium.

        Args:
            query: ConnectorQuery с params:
                - username: str (логин на Medium)
                - или full_name: str (поиск по имени)

        Returns:
            ConnectorResult с данными профиля
        """
        username = query.params.get("username")
        full_name = query.params.get("full_name")

        try:
            if username:
                result = await self._get_profile(username)
            elif full_name:
                result = await self._search_person(full_name)
            else:
                return ConnectorResult(
                    success=False,
                    source=self.name,
                    error="username or full_name is required",
                )

            return ConnectorResult(
                success=True,
                data=result,
                source=self.name,
                confidence=0.7,
            )

        except Exception as e:
            return ConnectorResult(
                success=False,
                source=self.name,
                error=str(e),
            )

    async def _get_profile(self, username: str) -> dict[str, Any]:
        """Получить профиль по username."""
        client = await self.get_client()

        response = await client.get(f"{self.BASE_URL}/@{username}")
        if response.status_code == 404:
            return {"found": False, "message": "Medium profile not found"}

        response.raise_for_status()
        soup = BeautifulSoup(response.text, "lxml")

        profile = self._parse_profile(soup, username)

        # Получить статьи
        articles = await self._get_user_articles(username)
        profile["articles"] = articles

        return profile

    async def _search_person(self, full_name: str) -> dict[str, Any]:
        """Поиск человека по имени."""
        client = await self.get_client()

        search_url = f"{self.BASE_URL}/search?q={quote_plus(full_name)}"
        response = await client.get(search_url)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "lxml")

        # Найти автора в результатах
        author_link = soup.select_one("a[href*='/@']")
        if not author_link:
            return {"found": False, "message": "No authors found"}

        href = author_link.get("href", "")
        username_match = re.search(r"@([^/?]+)", href)
        if not username_match:
            return {"found": False, "message": "Could not extract username"}

        username = username_match.group(1)
        return await self._get_profile(username)

    def _parse_profile(self, soup: BeautifulSoup, username: str) -> dict[str, Any]:
        """Парсинг профиля Medium."""
        profile: dict[str, Any] = {
            "found": True,
            "username": username,
            "profile_url": f"{self.BASE_URL}/@{username}",
            "source": "medium",
        }

        # Имя
        name_el = soup.select_one("h1")
        if name_el:
            profile["full_name"] = name_el.get_text(strip=True)

        # Описание
        bio_el = soup.select_one("div.u-fontSize14")
        if bio_el:
            profile["bio"] = bio_el.get_text(strip=True)

        # Количество подписчиков
        followers_el = soup.select_one("a[href*='followers']")
        if followers_el:
            followers_text = followers_el.get_text(strip=True)
            followers_match = re.search(r"(\d+)", followers_text.replace(",", ""))
            if followers_match:
                profile["followers"] = int(followers_match.group(1))

        return profile

    async def _get_user_articles(self, username: str) -> list[dict[str, Any]]:
        """Получить статьи пользователя."""
        client = await self.get_client()

        response = await client.get(f"{self.BASE_URL}/@{username}")
        if response.status_code != 200:
            return []

        soup = BeautifulSoup(response.text, "lxml")
        articles = []

        for article_el in soup.select("article"):
            title_el = article_el.select_one("h2")
            if not title_el:
                continue

            title = title_el.get_text(strip=True)

            link_el = article_el.select_one("a[href*='medium.com']")
            url = link_el.get("href", "") if link_el else ""

            # Дата
            date_el = article_el.select_one("time")
            date = date_el.get("datetime") if date_el else None

            # Время чтения
            read_time_el = article_el.select_one("span")
            read_time = None
            if read_time_el:
                rt_match = re.search(r"(\d+)", read_time_el.get_text(strip=True))
                if rt_match:
                    read_time = int(rt_match.group(1))

            articles.append({
                "title": title,
                "url": url,
                "platform": "medium",
                "date": date,
                "read_time_min": read_time,
                "tags": [],
            })

        return articles[:20]

    async def health_check(self) -> bool:
        """Проверка доступности Medium."""
        try:
            client = await self.get_client()
            response = await client.get(self.BASE_URL, timeout=10.0)
            return response.status_code == 200
        except Exception:
            return False


class MockMediumConnector(BaseConnector):
    """Mock Medium connector для тестирования."""

    MOCK_DATA: dict[str, dict[str, Any]] = {
        "Иванов Иван Иванович": {
            "found": True,
            "username": "ivanov_ml",
            "full_name": "Ivan Ivanov",
            "bio": "ML Engineer, tech writer",
            "followers": 1500,
            "profile_url": "https://medium.com/@ivanov_ml",
            "articles": [
                {
                    "title": "How to Deploy ML Models in Production",
                    "url": "https://medium.com/@ivanov_ml/how-to-deploy-ml-models-12345",
                    "platform": "medium",
                    "date": "2024-03-15T00:00:00",
                    "read_time_min": 8,
                    "tags": ["MLOps", "DevOps"],
                },
                {
                    "title": "Understanding Transformers Architecture",
                    "url": "https://medium.com/@ivanov_ml/understanding-transformers-67890",
                    "platform": "medium",
                    "date": "2023-11-20T00:00:00",
                    "read_time_min": 12,
                    "tags": ["Deep Learning", "NLP"],
                },
            ],
            "source": "medium",
        },
    }

    @property
    def name(self) -> str:
        return "medium"

    @property
    def rate_limit(self) -> int:
        return 1000

    async def fetch(self, query: ConnectorQuery) -> ConnectorResult:
        """Вернуть mock данные Medium."""
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
            data={"found": False, "message": "Medium profile not found"},
            source=f"{self.name}:mock",
        )

    async def health_check(self) -> bool:
        return True
