"""Candidate Ranker — ранжирование кандидатов при disambiguation.

Scoring:
- ФИО точно: +30
- ФИО fuzzy (>80%): +20
- Никнейм совпал: +25
- Компания совпала: +15
- Должность совпала: +10
- Город совпал: +10
- Навыки совпали: +10
"""

from rapidfuzz import fuzz

from person_osint.models import CandidateMatch, ConnectorResult


class CandidateRanker:
    """Ранжирование кандидатов по совпадениям с запросом."""

    def rank(
        self,
        query_full_name: str,
        query_company: str | None = None,
        query_position: str | None = None,
        query_city: str | None = None,
        query_skills: list[str] | None = None,
        query_nicknames: list[str] | None = None,
        results: dict[str, ConnectorResult] | None = None,
    ) -> list[CandidateMatch]:
        """Ранжировать найденных кандидатов.

        Args:
            query_full_name: ФИО из запроса
            query_company: Компания из запроса
            query_position: Должность из запроса
            query_city: Город из запроса
            query_skills: Навыки из запроса
            query_nicknames: Никнеймы из запроса
            results: Результаты коннекторов

        Returns:
            Отсортированный список CandidateMatch
        """
        candidates: list[CandidateMatch] = []

        # Собираем кандидатов из VK
        if results and "vk" in results:
            vk = results["vk"]
            if vk.success and vk.data and vk.data.get("found"):
                for user in vk.data.get("users", []):
                    match = self._score_vk_user(
                        user, query_full_name, query_company,
                        query_position, query_city, query_skills,
                    )
                    candidates.append(match)

        # Собираем кандидатов из LinkedIn
        if results and "linkedin" in results:
            li = results["linkedin"]
            if li.success and li.data and li.data.get("found"):
                match = self._score_linkedin_profile(
                    li.data, query_full_name, query_company,
                    query_position, query_city, query_skills,
                )
                candidates.append(match)

        # Собираем кандидатов из GitHub
        if results and "github" in results:
            gh = results["github"]
            if gh.success and gh.data and gh.data.get("found"):
                match = self._score_github_profile(
                    gh.data, query_full_name, query_company,
                    query_position, query_city, query_skills,
                )
                candidates.append(match)

        for candidate in candidates:
            candidate.is_demo = any(
                ":mock" in results[source].source
                for source in candidate.found_sources if source in results
            )
        candidates.sort(key=lambda x: x.match_score, reverse=True)
        seen = set()
        unique = []
        for candidate in candidates:
            key = tuple(sorted(candidate.selected_accounts.items()))
            if not key or key not in seen:
                unique.append(candidate)
                if key:
                    seen.add(key)

        return unique[:10]

    def _score_vk_user(
        self, user: dict, full_name: str, company: str | None,
        position: str | None, city: str | None, skills: list[str] | None,
    ) -> CandidateMatch:
        """Score VK пользователя."""
        score = 0
        matched = []

        # Имя
        user_name = user.get("full_name", "")
        name_ratio = fuzz.ratio(full_name.lower(), user_name.lower())
        if name_ratio >= 90:
            score += 30
            matched.append("name")
        elif name_ratio >= 70:
            score += 20
            matched.append("name_fuzzy")

        # Компания
        if company and user.get("current_company"):
            if company.lower() in user["current_company"].lower():
                score += 15
                matched.append("company")

        # Должность
        if position and user.get("current_position"):
            if position.lower() in user["current_position"].lower():
                score += 10
                matched.append("position")

        # Город
        if city and user.get("city"):
            if city.lower() in user["city"].lower():
                score += 10
                matched.append("city")

        return CandidateMatch(
            full_name=user_name,
            match_score=score,
            matched_fields=matched,
            current_position=user.get("current_position"),
            current_company=user.get("current_company"),
            city=user.get("city"),
            selected_accounts={"vk": str(user["user_id"])} if user.get("user_id") else {},
            found_sources=["vk"],
            photo_url=user.get("photo_url"),
        )

    def _score_linkedin_profile(
        self, data: dict, full_name: str, company: str | None,
        position: str | None, city: str | None, skills: list[str] | None,
    ) -> CandidateMatch:
        """Score LinkedIn профиля."""
        score = 0
        matched = []

        # Имя
        li_name = data.get("full_name", "")
        name_ratio = fuzz.ratio(full_name.lower(), li_name.lower())
        if name_ratio >= 90:
            score += 30
            matched.append("name")
        elif name_ratio >= 70:
            score += 20
            matched.append("name_fuzzy")

        # Компания
        if company and data.get("current_company"):
            if company.lower() in data["current_company"].lower():
                score += 15
                matched.append("company")

        # Должность
        if position and data.get("current_position"):
            if position.lower() in data["current_position"].lower():
                score += 10
                matched.append("position")

        # Город
        if city and data.get("city"):
            if city.lower() in data["city"].lower():
                score += 10
                matched.append("city")

        # Навыки
        if skills:
            li_skills = [s.get("name", "").lower() for s in data.get("skills", [])]
            matched_skills = sum(1 for s in skills if s.lower() in li_skills)
            if matched_skills > 0:
                score += min(matched_skills * 5, 10)
                matched.append("skills")

        # Никнейм — самый надёжный
        score += 25
        matched.append("linkedin_profile")

        return CandidateMatch(
            full_name=li_name,
            match_score=score,
            matched_fields=matched,
            current_position=data.get("current_position"),
            current_company=data.get("current_company"),
            city=data.get("city"),
            skills_preview=[s.get("name", "") for s in data.get("skills", [])[:5]],
            selected_accounts={"linkedin": data["profile_url"]} if data.get("profile_url") else {},
            found_sources=["linkedin"],
            photo_url=data.get("profile_picture"),
        )

    def _score_github_profile(
        self, data: dict, full_name: str, company: str | None,
        position: str | None, city: str | None, skills: list[str] | None,
    ) -> CandidateMatch:
        """Score GitHub профиля."""
        score = 0
        matched = []

        # Имя
        gh_name = data.get("full_name", "") or data.get("username", "")
        name_ratio = fuzz.ratio(full_name.lower(), gh_name.lower())
        if name_ratio >= 90:
            score += 30
            matched.append("name")
        elif name_ratio >= 70:
            score += 20
            matched.append("name_fuzzy")

        # Компания
        if company and data.get("company"):
            if company.lower() in data["company"].lower():
                score += 15
                matched.append("company")

        # Город
        if city and data.get("location"):
            if city.lower() in data["location"].lower():
                score += 10
                matched.append("city")

        # Навыки (языки)
        if skills:
            gh_langs = [l.lower() for l in data.get("top_languages", [])]
            matched_skills = sum(1 for s in skills if s.lower() in gh_langs)
            if matched_skills > 0:
                score += min(matched_skills * 5, 10)
                matched.append("skills")

        # GitHub — надёжный источник
        score += 25
        matched.append("github_profile")

        return CandidateMatch(
            full_name=gh_name,
            match_score=score,
            matched_fields=matched,
            current_company=data.get("company"),
            city=data.get("location"),
            skills_preview=data.get("top_languages", [])[:5],
            selected_accounts={"github": data["username"]} if data.get("username") else {},
            found_sources=["github"],
            photo_url=data.get("avatar_url"),
        )
