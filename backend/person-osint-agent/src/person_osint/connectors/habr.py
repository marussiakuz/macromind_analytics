"""Habr Connector — получение данных из Habr (habr.com).

Источник: https://habr.com

Получает:
- Профиль: карма, рейтинг, специализация, компания
- Статьи: заголовки, теги, просмотры, дата
- Комментарии (для анализа экспертизы)

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


class HabrConnector(BaseConnector):
    """Habr — парсинг habr.com."""

    BASE_URL = "https://habr.com"

    @property
    def name(self) -> str:
        return "habr"

    @property
    def rate_limit(self) -> int:
        return 60  # ~1 request per second

    async def fetch(self, query: ConnectorQuery) -> ConnectorResult:
        """Получить данные из Habr.

        Args:
            query: ConnectorQuery с params:
                - username: str (логин на Habr)
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
                confidence=0.8,
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

        response = await client.get(f"{self.BASE_URL}/ru/users/{username}/")
        if response.status_code == 404:
            return {"found": False, "message": "Habr profile not found"}

        response.raise_for_status()
        soup = BeautifulSoup(response.text, "lxml")

        profile = self._parse_profile(soup, username)

        # Получить статьи пользователя
        articles = await self._get_user_articles(username)
        profile["articles"] = articles

        return profile

    async def _search_person(self, full_name: str) -> dict[str, Any]:
        """Поиск человека по имени."""
        client = await self.get_client()

        # Habr поиск по людям (URL изменился)
        search_url = f"{self.BASE_URL}/ru/search/?q={quote_plus(full_name)}&type=users"
        response = await client.get(search_url)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "lxml")

        # Найти первый результат
        user_link = soup.select_one("a.tm-user-snippet__username")
        if not user_link:
            return {"found": False, "message": "No users found"}

        href = user_link.get("href", "")
        username_match = re.search(r"/users/([^/]+)/", href)
        if not username_match:
            return {"found": False, "message": "Could not extract username"}

        username = username_match.group(1)
        return await self._get_profile(username)

    def _parse_profile(self, soup: BeautifulSoup, username: str) -> dict[str, Any]:
        """Парсинг профиля Habr."""
        profile: dict[str, Any] = {
            "found": True,
            "username": username,
            "profile_url": f"{self.BASE_URL}/ru/users/{username}/",
            "source": "habr",
        }

        # Имя
        name_el = soup.select_one("a.tm-user-snippet__username span")
        if name_el:
            profile["full_name"] = name_el.get_text(strip=True)

        # Специализация
        spec_el = soup.select_one(".tm-user-specialization")
        if spec_el:
            profile["specialization"] = spec_el.get_text(strip=True)

        # Карма
        karma_el = soup.select_one(".tm-karma__votes")
        if karma_el:
            try:
                profile["karma"] = float(karma_el.get_text(strip=True).replace(",", "."))
            except ValueError:
                pass

        # Рейтинг
        rating_el = soup.select_one(".tm-rating__votes")
        if rating_el:
            try:
                profile["rating"] = float(rating_el.get_text(strip=True).replace(",", "."))
            except ValueError:
                pass

        # Компания
        company_el = soup.select_one("a.tm-user-company")
        if company_el:
            profile["company"] = company_el.get_text(strip=True)

        # Местоположение
        location_el = soup.select_one(".tm-user-location")
        if location_el:
            profile["city"] = location_el.get_text(strip=True)

        # Дата регистрации
        reg_el = soup.select_one(".tm-user-registration-date time")
        if reg_el:
            profile["registered_at"] = reg_el.get("datetime")

        return profile

    async def _get_user_articles(self, username: str) -> list[dict[str, Any]]:
        """Получить статьи пользователя."""
        client = await self.get_client()

        response = await client.get(f"{self.BASE_URL}/ru/users/{username}/publications/")
        if response.status_code != 200:
            return []

        soup = BeautifulSoup(response.text, "lxml")
        articles = []

        for article_el in soup.select("article.tm-articles-list__item"):
            title_el = article_el.select_one("h2 a")
            if not title_el:
                continue

            title = title_el.get_text(strip=True)
            url = title_el.get("href", "")
            if url and not url.startswith("http"):
                url = f"{self.BASE_URL}{url}"

            # Дата
            date_el = article_el.select_one("time")
            date = date_el.get("datetime") if date_el else None

            # Теги
            tags = [t.get_text(strip=True) for t in article_el.select("a.tm-tags-list__link")]

            # Просмотры
            views_el = article_el.select_one(".tm-icon-views")
            views = None
            if views_el:
                views_text = views_el.get_text(strip=True)
                views_match = re.search(r"(\d+)", views_text.replace(" ", ""))
                if views_match:
                    views = int(views_match.group(1))

            articles.append({
                "title": title,
                "url": url,
                "platform": "habr",
                "date": date,
                "views": views,
                "tags": tags,
            })

        return articles[:20]  # Ограничиваем до 20 статей

    async def health_check(self) -> bool:
        """Проверка доступности Habr."""
        try:
            client = await self.get_client()
            response = await client.get(f"{self.BASE_URL}/ru/", timeout=10.0)
            return response.status_code == 200
        except Exception:
            return False


class MockHabrConnector(BaseConnector):
    """Mock Habr connector для тестирования."""

    MOCK_DATA: dict[str, dict[str, Any]] = {
        "Иванов Иван Иванович": {
            "found": True,
            "username": "ivanov_cto",
            "full_name": "Иванов Иван Иванович",
            "specialization": "System Architecture, Python, ML",
            "karma": 125.5,
            "rating": 85.3,
            "company": "Яндекс",
            "city": "Москва",
            "registered_at": "2015-03-10T00:00:00",
            "profile_url": "https://habr.com/ru/users/ivanov_cto/",
            "articles": [
                {
                    "title": "Как мы делали микросервисы в Яндексе",
                    "url": "https://habr.com/ru/articles/12345/",
                    "platform": "habr",
                    "date": "2024-01-15T00:00:00",
                    "views": 15000,
                    "tags": ["микросервисы", "архитектура", "python"],
                },
                {
                    "title": "ML в продакшене: наш опыт",
                    "url": "https://habr.com/ru/articles/12346/",
                    "platform": "habr",
                    "date": "2023-06-20T00:00:00",
                    "views": 8500,
                    "tags": ["machine-learning", "mlops", "python"],
                },
            ],
            "source": "habr",
        },
    }

    @property
    def name(self) -> str:
        return "habr"

    @property
    def rate_limit(self) -> int:
        return 1000

    async def fetch(self, query: ConnectorQuery) -> ConnectorResult:
        """Вернуть mock данные Habr."""
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
            data={"found": False, "message": "Habr profile not found"},
            source=f"{self.name}:mock",
        )

    async def health_check(self) -> bool:
        return True
