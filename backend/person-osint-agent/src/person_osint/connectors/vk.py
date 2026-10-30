"""VK Connector — получение данных из VK API.

Источник: https://vk.com/dev/methods

Получает:
- users.search — поиск по ФИО с фильтрами
- users.get — расширенная информация о пользователе
- friends.get — список друзей
- friends.getMutual — общие друзья

Ограничения:
- Service token: 5000 requests/day
- Ключ хранится в .env (VK_SERVICE_TOKEN)
"""

from typing import Any

from person_osint.connectors.base import BaseConnector
from person_osint.models import ConnectorQuery, ConnectorResult


class VKConnector(BaseConnector):
    """VK API."""

    BASE_URL = "https://api.vk.com/method"

    @property
    def name(self) -> str:
        return "vk"

    @property
    def rate_limit(self) -> int:
        return 100  # ~3 requests per second

    async def fetch(self, query: ConnectorQuery) -> ConnectorResult:
        """Получить данные из VK.

        Args:
            query: ConnectorQuery с params:
                - action: str ("search", "get", "friends", "mutual_friends")
                - full_name: str (для поиска)
                - user_id: int (для get/friends)
                - city: str (опционально)
                - age_from: int (опционально)
                - age_to: int (опционально)

        Returns:
            ConnectorResult с данными VK
        """
        from person_osint.config import settings

        token = settings.vk_service_token
        if not token:
            return ConnectorResult(
                success=True,
                data={"found": False, "skipped": True, "reason": "VK token not configured"},
                source=f"{self.name}:skipped",
                confidence=0.0,
            )

        action = query.params.get("action", "search")

        try:
            if action == "search":
                result = await self._search(query.params, token)
            elif action == "get":
                result = await self._get_user(query.params, token)
            elif action == "friends":
                result = await self._get_friends(query.params, token)
            elif action == "mutual_friends":
                result = await self._get_mutual_friends(query.params, token)
            else:
                return ConnectorResult(
                    success=False,
                    source=self.name,
                    error=f"Unknown action: {action}",
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

    async def _search(self, params: dict[str, Any], token: str) -> dict[str, Any]:
        """Поиск пользователей по ФИО (OSINT F.2.1: от большего к меньшему)."""
        client = await self.get_client()

        full_name = params.get("full_name", "")
        city = params.get("city")
        age_from = params.get("age_from")
        age_to = params.get("age_to")

        # Принцип «от большего к меньшему»: сначала без фильтров
        vk_params: dict[str, Any] = {
            "q": full_name,
            "count": params.get("count", 20),
            "fields": "city,education,occupation,career,contacts,photo_200",
            "access_token": token,
            "v": "5.131",
        }

        # Добавляем фильтры последовательно
        if city:
            vk_params["hometown"] = city
        if age_from:
            vk_params["age_from"] = age_from
        if age_to:
            vk_params["age_to"] = age_to

        response = await client.get(f"{self.BASE_URL}/users.search", params=vk_params)
        response.raise_for_status()

        data = response.json()
        if "error" in data:
            return {"found": False, "error": data["error"]["error_msg"]}

        items = data.get("response", {}).get("items", [])

        users = []
        for user in items:
            users.append(self._normalize_user(user))

        return {
            "found": len(users) > 0,
            "total_count": data.get("response", {}).get("count", 0),
            "users": users,
            "source": "vk",
        }

    async def _get_user(self, params: dict[str, Any], token: str) -> dict[str, Any]:
        """Получить расширенную информацию о пользователе (OSINT F.4)."""
        client = await self.get_client()

        user_id = params.get("user_id")
        if not user_id:
            return {"found": False, "error": "user_id required"}

        response = await client.get(
            f"{self.BASE_URL}/users.get",
            params={
                "user_ids": user_id,
                "fields": "city,education,occupation,career,contacts,photo_200,counters,last_seen",
                "access_token": token,
                "v": "5.131",
            },
        )
        response.raise_for_status()

        data = response.json()
        if "error" in data:
            return {"found": False, "error": data["error"]["error_msg"]}

        users = data.get("response", [])
        if not users:
            return {"found": False, "message": "User not found"}

        return {"found": True, "user": self._normalize_user(users[0]), "source": "vk"}

    async def _get_friends(self, params: dict[str, Any], token: str) -> dict[str, Any]:
        """Получить список друзей (OSINT G.1)."""
        client = await self.get_client()

        user_id = params.get("user_id")
        if not user_id:
            return {"found": False, "error": "user_id required"}

        response = await client.get(
            f"{self.BASE_URL}/friends.get",
            params={
                "user_id": user_id,
                "count": params.get("count", 100),
                "fields": "city,photo_200",
                "access_token": token,
                "v": "5.131",
            },
        )
        response.raise_for_status()

        data = response.json()
        if "error" in data:
            return {"found": False, "error": data["error"]["error_msg"]}

        items = data.get("response", {}).get("items", [])
        friends = [self._normalize_user(u) for u in items]

        return {
            "found": True,
            "total_count": data.get("response", {}).get("count", 0),
            "friends": friends,
            "source": "vk",
        }

    async def _get_mutual_friends(self, params: dict[str, Any], token: str) -> dict[str, Any]:
        """Получить общих друзей (OSINT G.2)."""
        client = await self.get_client()

        source_uid = params.get("source_uid")
        target_uid = params.get("target_uid")

        if not source_uid or not target_uid:
            return {"found": False, "error": "source_uid and target_uid required"}

        response = await client.get(
            f"{self.BASE_URL}/friends.getMutual",
            params={
                "source_uid": source_uid,
                "target_uid": target_uid,
                "access_token": token,
                "v": "5.131",
            },
        )
        response.raise_for_status()

        data = response.json()
        if "error" in data:
            return {"found": False, "error": data["error"]["error_msg"]}

        mutual_ids = data.get("response", [])

        return {
            "found": True,
            "mutual_friends_count": len(mutual_ids),
            "mutual_friend_ids": mutual_ids,
            "source": "vk",
        }

    def _normalize_user(self, data: dict[str, Any]) -> dict[str, Any]:
        """Нормализовать данные пользователя VK."""
        city = data.get("city")
        occupation = data.get("occupation")
        career = data.get("career", [])

        current_company = None
        current_position = None
        if occupation:
            current_company = occupation.get("name")
            current_position = occupation.get("type")
        elif career:
            last = career[-1] if career else {}
            current_company = last.get("company")
            current_position = last.get("position")

        return {
            "user_id": data.get("id"),
            "first_name": data.get("first_name"),
            "last_name": data.get("last_name"),
            "full_name": f"{data.get('first_name', '')} {data.get('last_name', '')}".strip(),
            "city": city.get("title") if city else None,
            "current_company": current_company,
            "current_position": current_position,
            "photo_url": data.get("photo_200"),
            "profile_url": f"https://vk.com/id{data.get('id')}",
            "is_closed": data.get("is_closed", False),
            "source": "vk",
        }

    async def health_check(self) -> bool:
        """Проверка доступности VK API."""
        from person_osint.config import settings

        if not settings.vk_service_token:
            return False

        try:
            client = await self.get_client()
            response = await client.get(
                f"{self.BASE_URL}/users.get",
                params={
                    "user_ids": 1,
                    "access_token": settings.vk_service_token,
                    "v": "5.131",
                },
                timeout=10.0,
            )
            return response.status_code == 200
        except Exception:
            return False


class MockVKConnector(BaseConnector):
    """Mock VK connector для тестирования."""

    MOCK_DATA: dict[str, dict[str, Any]] = {
        "Иванов Иван Иванович": {
            "found": True,
            "total_count": 15000,
            "users": [
                {
                    "user_id": 123456,
                    "first_name": "Иван",
                    "last_name": "Иванов",
                    "full_name": "Иван Иванов",
                    "city": "Москва",
                    "current_company": "Яндекс",
                    "current_position": "CTO",
                    "photo_url": "https://pp.vk.me/12345.jpg",
                    "profile_url": "https://vk.com/id123456",
                    "is_closed": False,
                    "source": "vk",
                },
                {
                    "user_id": 789012,
                    "first_name": "Иван",
                    "last_name": "Иванов",
                    "full_name": "Иван Иванов",
                    "city": "Санкт-Петербург",
                    "current_company": None,
                    "current_position": None,
                    "photo_url": None,
                    "profile_url": "https://vk.com/id789012",
                    "is_closed": False,
                    "source": "vk",
                },
            ],
            "source": "vk",
        },
    }

    @property
    def name(self) -> str:
        return "vk"

    @property
    def rate_limit(self) -> int:
        return 1000

    async def fetch(self, query: ConnectorQuery) -> ConnectorResult:
        """Вернуть mock данные VK."""
        import asyncio
        await asyncio.sleep(0.05)

        action = query.params.get("action", "search")

        if action == "search":
            full_name = query.params.get("full_name")
            if full_name and full_name in self.MOCK_DATA:
                return ConnectorResult(
                    success=True,
                    data=self.MOCK_DATA[full_name],
                    source=f"{self.name}:mock",
                )
            return ConnectorResult(
                success=True,
                data={"found": False, "total_count": 0, "users": []},
                source=f"{self.name}:mock",
            )

        if action == "mutual_friends":
            return ConnectorResult(
                success=True,
                data={
                    "found": True,
                    "mutual_friends_count": 5,
                    "mutual_friend_ids": [111, 222, 333, 444, 555],
                },
                source=f"{self.name}:mock",
            )

        return ConnectorResult(
            success=True,
            data={"found": False, "message": "Not implemented in mock"},
            source=f"{self.name}:mock",
        )

    async def health_check(self) -> bool:
        return True
