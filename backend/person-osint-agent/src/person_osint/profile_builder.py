"""Profile Builder — сборка PersonProfile из всех источников."""

from typing import Any

from person_osint.models import (
    PersonProfile, Skill, Experience, Education,
    GitHubProfile, Publication, Article, Book,
    SocialProfile, PersonConnection, RedFlag,
    CandidateMatch, ConnectorResult,
)


class ProfileBuilder:
    """Сборка PersonProfile из данных разных коннекторов."""

    def build_from_results(
        self,
        full_name: str,
        results: dict[str, ConnectorResult],
    ) -> PersonProfile:
        """Собрать профиль из результатов коннекторов.

        Args:
            full_name: ФИО человека
            results: Словарь {source_name: ConnectorResult}

        Returns:
            PersonProfile
        """
        profile = PersonProfile(full_name=full_name)
        sources = []
        for source, result in results.items():
            profile.source_details[source] = result.source
            data = result.data or {}
            if ":mock" in result.source:
                status = "demo"
                profile.is_demo = True
            elif ":unavailable" in result.source:
                status = "unavailable"
            elif not result.success:
                status = "error"
            elif data.get("skipped"):
                status = "not_checked"
            elif data.get("found") is False:
                status = "not_found"
            else:
                status = "ok"
            profile.source_statuses[source] = status

        # LinkedIn
        linkedin = results.get("linkedin")
        if linkedin and linkedin.success and linkedin.data and linkedin.data.get("found"):
            self._apply_linkedin(profile, linkedin.data)
            sources.append("linkedin")

        # Habr
        habr = results.get("habr")
        if habr and habr.success and habr.data and habr.data.get("found"):
            self._apply_habr(profile, habr.data)
            sources.append("habr")

        # VC
        vc = results.get("vc")
        if vc and vc.success and vc.data and vc.data.get("found"):
            self._apply_vc(profile, vc.data)
            sources.append("vc")

        # GitHub
        github = results.get("github")
        if github and github.success and github.data and github.data.get("found"):
            self._apply_github(profile, github.data)
            sources.append("github")

        # Scholar
        scholar = results.get("scholar")
        if scholar and scholar.success and scholar.data and scholar.data.get("found"):
            self._apply_scholar(profile, scholar.data)
            sources.append("scholar")

        # Books
        books = results.get("books")
        if books and books.success and books.data and books.data.get("found"):
            self._apply_books(profile, books.data)
            sources.append("books")

        # Medium
        medium = results.get("medium")
        if medium and medium.success and medium.data and medium.data.get("found"):
            self._apply_medium(profile, medium.data)
            sources.append("medium")

        # VK
        vk = results.get("vk")
        if vk and vk.success and vk.data and vk.data.get("found"):
            self._apply_vk(profile, vk.data)
            sources.append("vk")

        # OSINT проверки
        sanctions = results.get("sanctions")
        if sanctions and sanctions.success and sanctions.data and not sanctions.data.get("skipped"):
            self._apply_sanctions(profile, sanctions.data)

        courts = results.get("courts")
        if courts and courts.success and courts.data:
            self._apply_courts(profile, courts.data)

        fssp = results.get("fssp")
        if fssp and fssp.success and fssp.data:
            self._apply_fssp(profile, fssp.data)

        pep = results.get("pep")
        if pep and pep.success and pep.data and not pep.data.get("skipped"):
            self._apply_pep(profile, pep.data)

        news = results.get("news")
        if news and news.success and news.data:
            self._apply_news(profile, news.data)

        # Username scan
        username_scan = results.get("username_scan")
        if username_scan and username_scan.success and username_scan.data:
            self._apply_username_scan(profile, username_scan.data)

        profile.sources = sources

        # Генерируем name_variants
        from person_osint.name_variations import generate_name_variants
        profile.name_variants = generate_name_variants(full_name)

        # Собираем уникальные языки программирования
        profile.programming_languages = list(set(profile.programming_languages))

        return profile

    def _apply_linkedin(self, profile: PersonProfile, data: dict[str, Any]):
        """Применить данные LinkedIn."""
        if not profile.current_position:
            profile.current_position = data.get("current_position")
        if not profile.current_company:
            profile.current_company = data.get("current_company")

        for exp in data.get("experience", []):
            profile.experience.append(Experience(
                company=exp.get("company", ""),
                position=exp.get("position", ""),
                start_date=exp.get("start_date"),
                end_date=exp.get("end_date"),
                description=exp.get("description"),
                source="linkedin",
            ))

        for edu in data.get("education", []):
            profile.education.append(Education(
                institution=edu.get("institution", ""),
                degree=edu.get("degree"),
                field=edu.get("field"),
                start_year=edu.get("start_year"),
                end_year=edu.get("end_year"),
                source="linkedin",
            ))

        for skill in data.get("skills", []):
            profile.skills.append(Skill(
                name=skill.get("name", ""),
                level=skill.get("level"),
                evidence=skill.get("evidence", []),
            ))

        if data.get("profile_url"):
            profile.social_profiles.append(SocialProfile(
                platform="linkedin",
                url=data["profile_url"],
                name=data.get("full_name"),
                source="linkedin",
            ))

    def _apply_habr(self, profile: PersonProfile, data: dict[str, Any]):
        """Применить данные Habr."""
        for article in data.get("articles", []):
            profile.articles.append(Article(
                title=article.get("title", ""),
                url=article.get("url", ""),
                platform="habr",
                date=article.get("date"),
                views=article.get("views"),
                tags=article.get("tags", []),
            ))

        if data.get("profile_url"):
            profile.social_profiles.append(SocialProfile(
                platform="habr",
                url=data["profile_url"],
                username=data.get("username"),
                source="habr",
            ))

    def _apply_vc(self, profile: PersonProfile, data: dict[str, Any]):
        """Применить данные VC.ru."""
        for article in data.get("articles", []):
            profile.articles.append(Article(
                title=article.get("title", ""),
                url=article.get("url", ""),
                platform="vc",
                date=article.get("date"),
                views=article.get("views"),
                tags=article.get("tags", []),
            ))

    def _apply_github(self, profile: PersonProfile, data: dict[str, Any]):
        """Применить данные GitHub."""
        profile.github = GitHubProfile(
            username=data.get("username", ""),
            bio=data.get("bio"),
            company=data.get("company"),
            location=data.get("location"),
            blog=data.get("blog"),
            public_repos=data.get("public_repos", 0),
            followers=data.get("followers", 0),
            following=data.get("following", 0),
            top_languages=data.get("top_languages", []),
            notable_repos=data.get("notable_repos", []),
            url=data.get("profile_url", ""),
        )

        profile.programming_languages.extend(data.get("top_languages", []))

        if data.get("profile_url"):
            profile.social_profiles.append(SocialProfile(
                platform="github",
                url=data["profile_url"],
                username=data.get("username"),
                source="github",
            ))

    def _apply_scholar(self, profile: PersonProfile, data: dict[str, Any]):
        """Применить данные Scholar."""
        for pub in data.get("publications", []):
            profile.publications.append(Publication(
                title=pub.get("title", ""),
                authors=pub.get("authors", []),
                year=pub.get("year"),
                citations=pub.get("citations"),
                venue=pub.get("venue"),
                url=pub.get("url"),
            ))

    def _apply_books(self, profile: PersonProfile, data: dict[str, Any]):
        """Применить данные Books."""
        for book in data.get("books", []):
            profile.books.append(Book(
                title=book.get("title", ""),
                authors=book.get("authors", []),
                year=book.get("year"),
                publisher=book.get("publisher"),
                isbn=book.get("isbn"),
            ))

    def _apply_medium(self, profile: PersonProfile, data: dict[str, Any]):
        """Применить данные Medium."""
        for article in data.get("articles", []):
            profile.articles.append(Article(
                title=article.get("title", ""),
                url=article.get("url", ""),
                platform="medium",
                date=article.get("date"),
                tags=article.get("tags", []),
            ))

    def _apply_vk(self, profile: PersonProfile, data: dict[str, Any]):
        """Применить данные VK."""
        users = [data["user"]] if data.get("user") else data.get("users", [])
        if users:
            user = users[0]
            if not profile.current_company and user.get("current_company"):
                profile.current_company = user["current_company"]
            if not profile.current_position and user.get("current_position"):
                profile.current_position = user["current_position"]

            profile.social_profiles.append(SocialProfile(
                platform="vk",
                url=user.get("profile_url", ""),
                username=str(user.get("user_id", "")),
                name=user.get("full_name"),
                city=user.get("city"),
                source="vk",
            ))

    def _apply_sanctions(self, profile: PersonProfile, data: dict[str, Any]):
        """Применить данные санкций."""
        profile.is_sanctioned = data.get("is_sanctioned")
        profile.sanction_matches = data.get("matches", [])

        if profile.is_sanctioned:
            profile.red_flags.append(RedFlag(
                priority="CRITICAL",
                category="sanctions",
                description="Найден в санкционных списках",
                evidence={"matches": profile.sanction_matches},
                source="sanctions",
            ))

    def _apply_courts(self, profile: PersonProfile, data: dict[str, Any]):
        """Применить данные судов."""
        if data.get("has_cases"):
            profile.court_cases = data.get("arbitration_cases", []) + data.get("general_cases", [])

            for case in profile.court_cases:
                if case.get("amount", 0) > 5000000:
                    profile.red_flags.append(RedFlag(
                        priority="HIGH",
                        category="courts",
                        description=f"Судебный иск на сумму {case['amount']:,.0f} ₽",
                        evidence=case,
                        source="courts",
                    ))

    def _apply_fssp(self, profile: PersonProfile, data: dict[str, Any]):
        """Применить данные ФССП."""
        if data.get("has_productions"):
            profile.enforcement_proceedings = data.get("productions", [])

            total_debt = data.get("total_debt", 0)
            if total_debt > 1000000:
                profile.red_flags.append(RedFlag(
                    priority="HIGH",
                    category="fssp",
                    description=f"Исполнительные производства на сумму {total_debt:,.0f} ₽",
                    evidence={"total_debt": total_debt},
                    source="fssp",
                ))

    def _apply_pep(self, profile: PersonProfile, data: dict[str, Any]):
        """Применить данные PEP."""
        profile.is_pep = data.get("is_pep")
        if profile.is_pep:
            profile.red_flags.append(RedFlag(
                priority="MEDIUM",
                category="pep",
                description="Politically Exposed Person",
                evidence={"details": data.get("details", "")},
                source="pep",
            ))

    def _apply_news(self, profile: PersonProfile, data: dict[str, Any]):
        """Применить данные новостей."""
        profile.news_mentions = data.get("articles", [])

        if data.get("has_negative"):
            negative = [a for a in profile.news_mentions if a.get("is_negative")]
            for article in negative:
                profile.red_flags.append(RedFlag(
                    priority="HIGH",
                    category="news",
                    description=f"Негативные СМИ: {article.get('title', '')}",
                    evidence=article,
                    source="news",
                ))

    def _apply_username_scan(self, profile: PersonProfile, data: dict[str, Any]):
        """Применить данные username scan."""
        for p in data.get("profiles", []):
            if p.get("status") == "good":
                profile.social_profiles.append(SocialProfile(
                    platform=p.get("site", ""),
                    url=p.get("url", ""),
                    username=p.get("username"),
                    source="username_scan",
                ))
