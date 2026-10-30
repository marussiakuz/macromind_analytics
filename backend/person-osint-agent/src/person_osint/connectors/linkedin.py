"""LinkedIn Connector — получение данных из LinkedIn через Proxycurl API.

Источник: https://nubela.co/proxycurl

Получает:
- Опыт работы: компании, должности, даты
- Образование: вуз, степень, специальность
- Навыки из endorsements
- Сертификаты и лицензии

Ограничения:
- Proxycurl free plan: 100 credits/month
- Ключ хранится в .env (PROXYCURL_API_KEY)
"""

from typing import Any

import httpx

from person_osint.connectors.base import BaseConnector
from person_osint.models import ConnectorQuery, ConnectorResult


class LinkedInConnector(BaseConnector):
    """LinkedIn через Proxycurl API."""

    BASE_URL = "https://nubela.co/proxycurl/api"

    @property
    def name(self) -> str:
        return "linkedin"

    @property
    def rate_limit(self) -> int:
        return 30  # ~1 request per 2 seconds

    async def fetch(self, query: ConnectorQuery) -> ConnectorResult:
        """Получить данные LinkedIn профиля.

        Args:
            query: ConnectorQuery с params:
                - linkedin_url: str (URL профиля)
                - или full_name: str (поиск по имени)
                - или company: str (поиск по компании)

        Returns:
            ConnectorResult с данными профиля
        """
        from person_osint.config import settings

        api_key = settings.proxycurl_api_key
        if not api_key:
            return ConnectorResult(
                success=True,
                data={"found": False, "skipped": True, "reason": "Proxycurl API key not configured"},
                source=f"{self.name}:skipped",
                confidence=0.0,
            )

        linkedin_url = query.params.get("linkedin_url")
        full_name = query.params.get("full_name")
        company = query.params.get("company")

        try:
            if linkedin_url:
                result = await self._get_profile(linkedin_url, api_key)
            elif full_name:
                result = await self._search_person(full_name, company, api_key)
            else:
                return ConnectorResult(
                    success=False,
                    source=self.name,
                    error="linkedin_url or full_name is required",
                )

            return ConnectorResult(
                success=True,
                data=result,
                source=self.name,
                confidence=0.9,
            )

        except httpx.TimeoutException:
            return ConnectorResult(
                success=True,
                data={"found": False, "skipped": True, "reason": "LinkedIn API timeout"},
                source=f"{self.name}:timeout",
                confidence=0.0,
            )
        except httpx.HTTPStatusError as e:
            return ConnectorResult(
                success=True,
                data={"found": False, "skipped": True, "reason": f"LinkedIn API error: {e.response.status_code}"},
                source=f"{self.name}:error",
                confidence=0.0,
            )
        except Exception as e:
            return ConnectorResult(
                success=False,
                source=self.name,
                error=str(e),
            )

    async def _get_profile(self, linkedin_url: str, api_key: str) -> dict[str, Any]:
        """Получить профиль по URL."""
        client = await self.get_client()

        response = await client.get(
            f"{self.BASE_URL}/linkedin",
            params={"url": linkedin_url},
            headers={"Authorization": f"Bearer {api_key}"},
        )

        if response.status_code == 404:
            return {"found": False, "message": "LinkedIn profile not found"}

        response.raise_for_status()
        data = response.json()

        return self._normalize_profile(data)

    async def _search_person(
        self, full_name: str, company: str | None, api_key: str
    ) -> dict[str, Any]:
        """Поиск человека по имени."""
        client = await self.get_client()

        params: dict[str, Any] = {"keyword": full_name}
        if company:
            params["keyword"] = f"{full_name} {company}"

        response = await client.get(
            f"{self.BASE_URL}/search",
            params=params,
            headers={"Authorization": f"Bearer {api_key}"},
        )

        if response.status_code == 404:
            return {"found": False, "message": "No results found"}

        response.raise_for_status()
        data = response.json()

        results = data.get("results", [])
        if not results:
            return {"found": False, "message": "No results found"}

        # Берём первый результат и получаем полный профиль
        first = results[0]
        profile_url = first.get("profile_url") or first.get("url")
        if profile_url:
            return await self._get_profile(profile_url, api_key)

        return self._normalize_profile(first)

    def _normalize_profile(self, data: dict[str, Any]) -> dict[str, Any]:
        """Нормализовать данные Proxycurl в наш формат."""
        experience = []
        for exp in data.get("experiences", []):
            experience.append({
                "company": exp.get("company", ""),
                "position": exp.get("title", ""),
                "start_date": self._format_date(exp.get("starts_at")),
                "end_date": self._format_date(exp.get("ends_at")),
                "description": exp.get("description"),
                "source": "linkedin",
            })

        education = []
        for edu in data.get("education", []):
            education.append({
                "institution": edu.get("school", ""),
                "degree": edu.get("degree_name"),
                "field": edu.get("field_of_study"),
                "start_year": edu.get("starts_at", {}).get("year") if edu.get("starts_at") else None,
                "end_year": edu.get("ends_at", {}).get("year") if edu.get("ends_at") else None,
                "source": "linkedin",
            })

        skills = []
        for skill in data.get("skills", []):
            skills.append({
                "name": skill.get("name", ""),
                "level": None,
                "evidence": ["linkedin_endorsement"],
                "source": "linkedin",
            })

        current_company = None
        current_position = None
        if experience:
            current_company = experience[0].get("company")
            current_position = experience[0].get("position")

        return {
            "found": True,
            "full_name": data.get("full_name"),
            "first_name": data.get("first_name"),
            "last_name": data.get("last_name"),
            "headline": data.get("headline"),
            "summary": data.get("summary"),
            "city": data.get("city"),
            "country": data.get("country"),
            "current_company": current_company,
            "current_position": current_position,
            "experience": experience,
            "education": education,
            "skills": skills,
            "profile_url": data.get("profile_url") or data.get("url"),
            "profile_picture": data.get("profile_picture"),
            "connections_count": data.get("connections_count"),
            "recommendations_count": len(data.get("recommendations", [])),
            "source": "linkedin",
        }

    def _format_date(self, date_obj: Any) -> str | None:
        """Форматировать дату из Proxycurl."""
        if not date_obj:
            return None
        if isinstance(date_obj, dict):
            year = date_obj.get("year")
            month = date_obj.get("month")
            if year and month:
                return f"{year}-{month:02d}"
            return str(year) if year else None
        return str(date_obj)

    async def health_check(self) -> bool:
        """Проверка доступности Proxycurl API."""
        from person_osint.config import settings

        if not settings.proxycurl_api_key:
            return False

        try:
            client = await self.get_client()
            response = await client.get(
                f"{self.BASE_URL}/linkedin",
                params={"url": "https://www.linkedin.com/in/williamhgates/"},
                headers={"Authorization": f"Bearer {settings.proxycurl_api_key}"},
                timeout=10.0,
            )
            return response.status_code in (200, 429)
        except Exception:
            return False


class MockLinkedInConnector(BaseConnector):
    """Mock LinkedIn connector для тестирования."""

    MOCK_DATA: dict[str, dict[str, Any]] = {
        "Иванов Иван Иванович": {
            "found": True,
            "full_name": "Иванов Иван Иванович",
            "first_name": "Иван",
            "last_name": "Иванов",
            "headline": "CTO @ Яндекс | Python | ML",
            "summary": "15+ лет опыта в разработке. Руководил командами до 50 человек.",
            "city": "Москва",
            "country": "Russia",
            "current_company": "Яндекс",
            "current_position": "CTO",
            "experience": [
                {
                    "company": "Яндекс",
                    "position": "CTO",
                    "start_date": "2020-01",
                    "end_date": None,
                    "description": "Руководство технической командой",
                    "source": "linkedin",
                },
                {
                    "company": "Google",
                    "position": "Senior Software Engineer",
                    "start_date": "2015-03",
                    "end_date": "2019-12",
                    "description": "Разработка поисковых алгоритмов",
                    "source": "linkedin",
                },
            ],
            "education": [
                {
                    "institution": "МГУ",
                    "degree": "Магистр",
                    "field": "Прикладная математика",
                    "start_year": 2005,
                    "end_year": 2010,
                    "source": "linkedin",
                },
            ],
            "skills": [
                {"name": "Python", "level": "expert", "evidence": ["linkedin_endorsement"], "source": "linkedin"},
                {"name": "Machine Learning", "level": "expert", "evidence": ["linkedin_endorsement"], "source": "linkedin"},
                {"name": "Kubernetes", "level": "senior", "evidence": ["linkedin_endorsement"], "source": "linkedin"},
                {"name": "System Architecture", "level": "expert", "evidence": ["linkedin_endorsement"], "source": "linkedin"},
            ],
            "profile_url": "https://linkedin.com/in/ivanov-ivan",
            "profile_picture": None,
            "connections_count": 500,
            "recommendations_count": 12,
            "source": "linkedin",
        },
        "Петров Петр Петрович": {
            "found": True,
            "full_name": "Петров Петр Петрович",
            "first_name": "Петр",
            "last_name": "Петров",
            "headline": "ML Engineer @ Sber",
            "summary": "Специалист по NLP и компьютерному зрению.",
            "city": "Санкт-Петербург",
            "country": "Russia",
            "current_company": "Сбер",
            "current_position": "ML Engineer",
            "experience": [
                {
                    "company": "Сбер",
                    "position": "ML Engineer",
                    "start_date": "2021-06",
                    "end_date": None,
                    "description": "Разработка NLP моделей",
                    "source": "linkedin",
                },
            ],
            "education": [
                {
                    "institution": "СПбГУ",
                    "degree": "Бакалавр",
                    "field": "Информатика",
                    "start_year": 2016,
                    "end_year": 2020,
                    "source": "linkedin",
                },
            ],
            "skills": [
                {"name": "Python", "level": "senior", "evidence": ["linkedin_endorsement"], "source": "linkedin"},
                {"name": "TensorFlow", "level": "senior", "evidence": ["linkedin_endorsement"], "source": "linkedin"},
                {"name": "NLP", "level": "expert", "evidence": ["linkedin_endorsement"], "source": "linkedin"},
            ],
            "profile_url": "https://linkedin.com/in/petrov-petr",
            "profile_picture": None,
            "connections_count": 200,
            "recommendations_count": 5,
            "source": "linkedin",
        },
    }

    @property
    def name(self) -> str:
        return "linkedin"

    @property
    def rate_limit(self) -> int:
        return 1000

    async def fetch(self, query: ConnectorQuery) -> ConnectorResult:
        """Вернуть mock данные LinkedIn."""
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
            data={"found": False, "message": "Profile not found"},
            source=f"{self.name}:mock",
        )

    async def health_check(self) -> bool:
        return True
