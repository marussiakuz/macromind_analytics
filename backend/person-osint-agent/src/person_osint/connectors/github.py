"""GitHub Connector — получение данных из GitHub API.

Источник: https://api.github.com

Получает:
- Профиль: bio, company, location, blog
- Репозитории: stars, forks, language, description
- Contributions: количество за год
- Top languages

Ограничения:
- Неаутентифицированный: 60 requests/hour
- Аутентифицированный: 5000 requests/hour
"""

from typing import Any

from person_osint.connectors.base import BaseConnector
from person_osint.models import ConnectorQuery, ConnectorResult


class GitHubConnector(BaseConnector):
    """GitHub API."""

    BASE_URL = "https://api.github.com"

    @property
    def name(self) -> str:
        return "github"

    @property
    def rate_limit(self) -> int:
        return 60  # 60 requests/hour без аутентификации

    async def fetch(self, query: ConnectorQuery) -> ConnectorResult:
        """Получить данные из GitHub.

        Args:
            query: ConnectorQuery с params:
                - username: str (логин на GitHub)
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
                result = await self._search_user(full_name)
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
                confidence=0.9,
            )

        except Exception as e:
            return ConnectorResult(
                success=False,
                source=self.name,
                error=str(e),
            )

    async def _search_user(self, full_name: str) -> dict[str, Any]:
        """Поиск пользователя по имени."""
        client = await self.get_client()

        response = await client.get(
            f"{self.BASE_URL}/search/users",
            params={"q": full_name, "per_page": 5},
        )
        response.raise_for_status()

        data = response.json()
        items = data.get("items", [])

        if not items:
            return {"found": False, "message": "No users found"}

        # Берём первый результат
        username = items[0]["login"]
        return await self._get_profile(username)

    async def _get_profile(self, username: str) -> dict[str, Any]:
        """Получить профиль по username."""
        client = await self.get_client()

        # Получить основные данные
        response = await client.get(f"{self.BASE_URL}/users/{username}")
        if response.status_code == 404:
            return {"found": False, "message": "GitHub user not found"}

        response.raise_for_status()
        user_data = response.json()

        profile = self._normalize_user(user_data)

        # Получить репозитории
        repos = await self._get_repos(username)
        profile["repos"] = repos
        profile["notable_repos"] = [r for r in repos if r.get("stars", 0) > 10]

        # Подсчитать top languages
        languages: dict[str, int] = {}
        for repo in repos:
            lang = repo.get("language")
            if lang:
                languages[lang] = languages.get(lang, 0) + 1
        profile["top_languages"] = sorted(languages.keys(), key=lambda x: languages[x], reverse=True)[:10]

        return profile

    async def _get_repos(self, username: str) -> list[dict[str, Any]]:
        """Получить репозитории пользователя."""
        client = await self.get_client()

        response = await client.get(
            f"{self.BASE_URL}/users/{username}/repos",
            params={"sort": "updated", "per_page": 30},
        )

        if response.status_code != 200:
            return []

        repos_data = response.json()
        repos = []

        for repo in repos_data:
            if repo.get("fork"):
                continue  # Пропускаем форки

            repos.append({
                "name": repo["name"],
                "full_name": repo["full_name"],
                "description": repo.get("description"),
                "url": repo["html_url"],
                "language": repo.get("language"),
                "stars": repo.get("stargazers_count", 0),
                "forks": repo.get("forks_count", 0),
                "watchers": repo.get("watchers_count", 0),
                "open_issues": repo.get("open_issues_count", 0),
                "created_at": repo.get("created_at"),
                "updated_at": repo.get("updated_at"),
                "pushed_at": repo.get("pushed_at"),
                "topics": repo.get("topics", []),
                "license": repo.get("license", {}).get("spdx_id") if repo.get("license") else None,
            })

        return repos

    def _normalize_user(self, data: dict[str, Any]) -> dict[str, Any]:
        """Нормализовать данные пользователя."""
        return {
            "found": True,
            "username": data["login"],
            "full_name": data.get("name"),
            "bio": data.get("bio"),
            "company": data.get("company"),
            "location": data.get("location"),
            "blog": data.get("blog"),
            "email": data.get("email"),
            "twitter_username": data.get("twitter_username"),
            "public_repos": data.get("public_repos", 0),
            "public_gists": data.get("public_gists", 0),
            "followers": data.get("followers", 0),
            "following": data.get("following", 0),
            "profile_url": data["html_url"],
            "avatar_url": data.get("avatar_url"),
            "created_at": data.get("created_at"),
            "updated_at": data.get("updated_at"),
            "source": "github",
        }

    async def health_check(self) -> bool:
        """Проверка доступности GitHub API."""
        try:
            client = await self.get_client()
            response = await client.get(f"{self.BASE_URL}/rate_limit", timeout=10.0)
            return response.status_code == 200
        except Exception:
            return False


class MockGitHubConnector(BaseConnector):
    """Mock GitHub connector для тестирования."""

    MOCK_DATA: dict[str, dict[str, Any]] = {
        "Иванов Иван Иванович": {
            "found": True,
            "username": "ivanov-dev",
            "full_name": "Ivan Ivanov",
            "bio": "Senior Software Engineer | Python | ML",
            "company": "Yandex",
            "location": "Moscow, Russia",
            "blog": "https://ivanov.dev",
            "email": "ivan@yandex.ru",
            "twitter_username": None,
            "public_repos": 42,
            "public_gists": 15,
            "followers": 350,
            "following": 120,
            "profile_url": "https://github.com/ivanov-dev",
            "avatar_url": "https://avatars.githubusercontent.com/u/12345",
            "created_at": "2015-03-10T00:00:00Z",
            "updated_at": "2024-06-01T00:00:00Z",
            "repos": [
                {
                    "name": "ml-pipeline",
                    "full_name": "ivanov-dev/ml-pipeline",
                    "description": "ML pipeline for production",
                    "url": "https://github.com/ivanov-dev/ml-pipeline",
                    "language": "Python",
                    "stars": 342,
                    "forks": 45,
                    "watchers": 342,
                    "open_issues": 12,
                    "created_at": "2022-01-15T00:00:00Z",
                    "updated_at": "2024-05-20T00:00:00Z",
                    "pushed_at": "2024-05-20T00:00:00Z",
                    "topics": ["machine-learning", "mlops", "python"],
                    "license": "MIT",
                },
                {
                    "name": "nlp-toolkit",
                    "full_name": "ivanov-dev/nlp-toolkit",
                    "description": "NLP utilities for Russian language",
                    "url": "https://github.com/ivanov-dev/nlp-toolkit",
                    "language": "Python",
                    "stars": 189,
                    "forks": 23,
                    "watchers": 189,
                    "open_issues": 5,
                    "created_at": "2021-06-20T00:00:00Z",
                    "updated_at": "2024-04-15T00:00:00Z",
                    "pushed_at": "2024-04-15T00:00:00Z",
                    "topics": ["nlp", "russian", "text-processing"],
                    "license": "MIT",
                },
                {
                    "name": "dotfiles",
                    "full_name": "ivanov-dev/dotfiles",
                    "description": "My configuration files",
                    "url": "https://github.com/ivanov-dev/dotfiles",
                    "language": "Shell",
                    "stars": 5,
                    "forks": 1,
                    "watchers": 5,
                    "open_issues": 0,
                    "created_at": "2020-01-01T00:00:00Z",
                    "updated_at": "2023-12-01T00:00:00Z",
                    "pushed_at": "2023-12-01T00:00:00Z",
                    "topics": [],
                    "license": None,
                },
            ],
            "notable_repos": [
                {
                    "name": "ml-pipeline",
                    "full_name": "ivanov-dev/ml-pipeline",
                    "description": "ML pipeline for production",
                    "url": "https://github.com/ivanov-dev/ml-pipeline",
                    "language": "Python",
                    "stars": 342,
                    "forks": 45,
                    "watchers": 342,
                    "open_issues": 12,
                    "created_at": "2022-01-15T00:00:00Z",
                    "updated_at": "2024-05-20T00:00:00Z",
                    "pushed_at": "2024-05-20T00:00:00Z",
                    "topics": ["machine-learning", "mlops", "python"],
                    "license": "MIT",
                },
                {
                    "name": "nlp-toolkit",
                    "full_name": "ivanov-dev/nlp-toolkit",
                    "description": "NLP utilities for Russian language",
                    "url": "https://github.com/ivanov-dev/nlp-toolkit",
                    "language": "Python",
                    "stars": 189,
                    "forks": 23,
                    "watchers": 189,
                    "open_issues": 5,
                    "created_at": "2021-06-20T00:00:00Z",
                    "updated_at": "2024-04-15T00:00:00Z",
                    "pushed_at": "2024-04-15T00:00:00Z",
                    "topics": ["nlp", "russian", "text-processing"],
                    "license": "MIT",
                },
            ],
            "top_languages": ["Python", "Shell", "JavaScript"],
            "source": "github",
        },
    }

    @property
    def name(self) -> str:
        return "github"

    @property
    def rate_limit(self) -> int:
        return 1000

    async def fetch(self, query: ConnectorQuery) -> ConnectorResult:
        """Вернуть mock данные GitHub."""
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
            data={"found": False, "message": "GitHub user not found"},
            source=f"{self.name}:mock",
        )

    async def health_check(self) -> bool:
        return True
