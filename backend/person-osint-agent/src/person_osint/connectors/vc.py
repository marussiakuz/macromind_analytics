"""VC Connector — получение данных из VC.ru (vc.ru).

Источник: https://vc.ru

Получает:
- Профиль автора
- Статьи и публикации

Ограничения:
- Парсинг HTML (нет официального API)
- Rate limiting: ~1 запрос в секунду
"""

import re
from typing import Any
from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from person_osint.connectors.base import BaseConnector
from person_osint.models import ConnectorQuery, ConnectorResult


class VCConnector(BaseConnector):
    """VC.ru — парсинг vc.ru."""

    BASE_URL = "https://vc.ru"

    @property
    def name(self) -> str:
        return "vc"

    @property
    def rate_limit(self) -> int:
        return 60

    async def fetch(self, query: ConnectorQuery) -> ConnectorResult:
        """Получить данные из VC.ru.

        Args:
            query: ConnectorQuery с params:
                - username: str (логин на VC.ru)
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

        response = await client.get(f"{self.BASE_URL}/user/{username}")
        if response.status_code == 404:
            return {"found": False, "message": "VC.ru profile not found"}

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

        search_url = f"{self.BASE_URL}/search?q={quote_plus(full_name)}&type=user"
        response = await client.get(search_url)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "lxml")

        # Найти первый результат
        user_link = soup.select_one("a.content-header-author")
        if not user_link:
            return {"found": False, "message": "No users found"}

        href = user_link.get("href", "")
        username_match = re.search(r"/user/([^/]+)", href)
        if not username_match:
            return {"found": False, "message": "Could not extract username"}

        username = username_match.group(1)
        return await self._get_profile(username)

    def _parse_profile(self, soup: BeautifulSoup, username: str) -> dict[str, Any]:
        """Парсинг профиля VC.ru."""
        profile: dict[str, Any] = {
            "found": True,
            "username": username,
            "profile_url": f"{self.BASE_URL}/user/{username}",
            "source": "vc",
        }

        # Имя
        name_el = soup.select_one(".profile-name")
        if name_el:
            profile["full_name"] = name_el.get_text(strip=True)

        # Описание
        desc_el = soup.select_one(".profile-description")
        if desc_el:
            profile["description"] = desc_el.get_text(strip=True)

        # Компания
        company_el = soup.select_one(".profile-company a")
        if company_el:
            profile["company"] = company_el.get_text(strip=True)

        # Должность
        position_el = soup.select_one(".profile-position")
        if position_el:
            profile["position"] = position_el.get_text(strip=True)

        # Рейтинг
        rating_el = soup.select_one(".profile-rating-value")
        if rating_el:
            try:
                profile["rating"] = float(rating_el.get_text(strip=True))
            except ValueError:
                pass

        return profile

    async def _get_user_articles(self, username: str) -> list[dict[str, Any]]:
        """Получить статьи пользователя."""
        client = await self.get_client()

        response = await client.get(f"{self.BASE_URL}/user/{username}/publications")
        if response.status_code != 200:
            return []

        soup = BeautifulSoup(response.text, "lxml")
        articles = []

        for article_el in soup.select("article.content-item"):
            title_el = article_el.select_one("a.content-title")
            if not title_el:
                continue

            title = title_el.get_text(strip=True)
            url = title_el.get("href", "")
            if url and not url.startswith("http"):
                url = f"{self.BASE_URL}{url}"

            # Дата
            date_el = article_el.select_one("time")
            date = date_el.get("datetime") if date_el else None

            articles.append({
                "title": title,
                "url": url,
                "platform": "vc",
                "date": date,
                "views": None,
                "tags": [],
            })

        return articles[:20]

    async def health_check(self) -> bool:
        """Проверка доступности VC.ru."""
        try:
            client = await self.get_client()
            response = await client.get(self.BASE_URL, timeout=10.0)
            return response.status_code == 200
        except Exception:
            return False


class MockVCConnector(BaseConnector):
    """Mock VC connector для тестирования."""

    MOCK_DATA: dict[str, dict[str, Any]] = {
        "Иванов Иван Иванович": {
            "found": True,
            "username": "ivanov_tech",
            "full_name": "Иванов Иван Иванович",
            "description": "CTO, архитектор, преподаватель",
            "company": "Яндекс",
            "position": "CTO",
            "rating": 92.0,
            "profile_url": "https://vc.ru/user/ivanov_tech",
            "articles": [
                {
                    "title": "Тренды в AI на 2024 год",
                    "url": "https://vc.ru/ai/567890",
                    "platform": "vc",
                    "date": "2024-02-10T00:00:00",
                    "views": 12000,
                    "tags": ["AI", "тренды"],
                },
            ],
            "source": "vc",
        },
    }

    @property
    def name(self) -> str:
        return "vc"

    @property
    def rate_limit(self) -> int:
        return 1000

    async def fetch(self, query: ConnectorQuery) -> ConnectorResult:
        """Вернуть mock данные VC.ru."""
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
            data={"found": False, "message": "VC.ru profile not found"},
            source=f"{self.name}:mock",
        )

    async def health_check(self) -> bool:
        return True
