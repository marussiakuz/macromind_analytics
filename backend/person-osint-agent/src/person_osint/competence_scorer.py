"""Competence Scorer — оценка компетенций человека (0-100).

Алгоритм (веса от пользователя):
- Опыт работы + должность: 30%
- Навыки + endorsements: 25%
- Публикации + статьи: 20%
- GitHub + код: 15%
- Образование: 10%
"""

from datetime import date

from person_osint.models import PersonProfile, CompetenceAssessment


class CompetenceScorer:
    """Оценка компетенций на основе данных профиля."""

    # Веса
    WEIGHT_EXPERIENCE = 0.30
    WEIGHT_SKILLS = 0.25
    WEIGHT_PUBLICATIONS = 0.20
    WEIGHT_GITHUB = 0.15
    WEIGHT_EDUCATION = 0.10

    def score(self, profile: PersonProfile) -> CompetenceAssessment:
        """Рассчитать score компетенций.

        Args:
            profile: PersonProfile с данными

        Returns:
            CompetenceAssessment с оценкой
        """
        experience_score = self._score_experience(profile)
        skills_score = self._score_skills(profile)
        publications_score = self._score_publications(profile)
        github_score = self._score_github(profile)
        education_score = self._score_education(profile)

        overall = (
            experience_score * self.WEIGHT_EXPERIENCE
            + skills_score * self.WEIGHT_SKILLS
            + publications_score * self.WEIGHT_PUBLICATIONS
            + github_score * self.WEIGHT_GITHUB
            + education_score * self.WEIGHT_EDUCATION
        )

        # Определяем сильные стороны и concerns
        strengths = []
        concerns = []

        if experience_score >= 70:
            strengths.append("Сильный опыт работы")
        elif experience_score < 30:
            concerns.append("Мало опыта")

        if skills_score >= 70:
            strengths.append("Много навыков с подтверждением")
        elif skills_score < 30:
            concerns.append("Мало подтверждённых навыков")

        if publications_score >= 70:
            strengths.append("Активная публикационная деятельность")
        elif publications_score == 0:
            concerns.append("Нет публикаций")

        if github_score >= 70:
            strengths.append("Активный open-source вклад")
        elif github_score == 0:
            concerns.append("Нет публичного кода")

        if education_score >= 70:
            strengths.append("Сильное образование")

        # Red flags влияют на score
        if profile.is_sanctioned:
            overall = min(overall, 10)
            concerns.append("Санкции (CRITICAL)")

        if profile.is_pep:
            concerns.append("PEP статус")

        if any(rf.priority == "HIGH" for rf in profile.red_flags):
            overall = min(overall, 50)

        return CompetenceAssessment(
            person_name=profile.full_name or "",
            overall_score=round(overall, 1),
            technical_score=round((skills_score + github_score) / 2, 1),
            experience_score=round(experience_score, 1),
            reputation_score=round(publications_score, 1),
            strengths=strengths,
            concerns=concerns,
            evidence_summary=self._build_summary(profile),
        )

    def _score_experience(self, profile: PersonProfile) -> float:
        """Оценка опыта работы (0-100)."""
        if not profile.experience:
            return 0

        score = 0

        # Количество мест работы
        count = len(profile.experience)
        score += min(count * 15, 45)  # до 45 за количество

        # Длительность опыта
        total_years = 0
        for exp in profile.experience:
            if exp.start_date:
                try:
                    start = date.fromisoformat(exp.start_date[:7] + "-01")
                    end = (date.fromisoformat(exp.end_date[:7] + "-01")
                           if exp.end_date else date.today())
                    months = (end.year - start.year) * 12 + end.month - start.month
                    total_years += max(0, months / 12)
                except (ValueError, IndexError):
                    pass

        score += min(total_years * 5, 35)  # до 35 за годы

        # Текущая должность
        if profile.current_position:
            position_lower = profile.current_position.lower()
            if any(p in position_lower for p in ["cto", "ceo", "founder", "директор", "руководитель"]):
                score += 20
            elif any(p in position_lower for p in ["senior", "lead", "head", "архитектор"]):
                score += 15
            elif any(p in position_lower for p in ["middle", "junior"]):
                score += 5

        return min(score, 100)

    def _score_skills(self, profile: PersonProfile) -> float:
        """Оценка навыков (0-100)."""
        if not profile.skills:
            return 0

        score = 0

        # Количество навыков
        count = len(profile.skills)
        score += min(count * 10, 40)

        # Уровень навыков
        expert_count = sum(1 for s in profile.skills if s.level == "expert")
        senior_count = sum(1 for s in profile.skills if s.level == "senior")
        score += expert_count * 15 + senior_count * 10

        # Evidence (подтверждения)
        with_evidence = sum(1 for s in profile.skills if s.evidence)
        score += min(with_evidence * 5, 20)

        return min(score, 100)

    def _score_publications(self, profile: PersonProfile) -> float:
        """Оценка публикаций (0-100)."""
        score = 0

        # Статьи на Habr/VC/Medium
        articles_count = len(profile.articles)
        score += min(articles_count * 5, 25)

        # Научные публикации
        pubs_count = len(profile.publications)
        score += min(pubs_count * 10, 30)

        # Цитирования
        total_citations = sum(p.citations or 0 for p in profile.publications)
        if total_citations > 100:
            score += 25
        elif total_citations > 50:
            score += 20
        elif total_citations > 10:
            score += 15
        elif total_citations > 0:
            score += 10

        # Книги
        books_count = len(profile.books)
        score += min(books_count * 10, 20)

        return min(score, 100)

    def _score_github(self, profile: PersonProfile) -> float:
        """Оценка GitHub (0-100)."""
        if not profile.github:
            return 0

        score = 0
        gh = profile.github

        # Количество репозиториев
        score += min(gh.public_repos * 2, 20)

        # Stars
        total_stars = sum(r.get("stars", 0) for r in gh.notable_repos)
        if total_stars > 500:
            score += 30
        elif total_stars > 100:
            score += 25
        elif total_stars > 50:
            score += 20
        elif total_stars > 10:
            score += 15

        # Followers
        score += min(gh.followers * 0.5, 20)

        # Top languages
        score += min(len(gh.top_languages) * 3, 15)

        # Notable repos
        score += min(len(gh.notable_repos) * 5, 15)

        return min(score, 100)

    def _score_education(self, profile: PersonProfile) -> float:
        """Оценка образования (0-100)."""
        if not profile.education:
            return 0

        score = 0

        for edu in profile.education:
            inst_lower = edu.institution.lower()

            # Престижные вузы
            if any(u in inst_lower for u in ["мгу", "спбгу", "мфти", "мгту", "вШЭ", "иннополис", "мisis"]):
                score += 30
            elif any(u in inst_lower for u in ["mit", "stanford", "berkeley", "cmu", "harvard"]):
                score += 40
            else:
                score += 15

            # Степень
            if edu.degree:
                degree_lower = edu.degree.lower()
                if "доктор" in degree_lower or "phd" in degree_lower:
                    score += 30
                elif "магистр" in degree_lower or "master" in degree_lower:
                    score += 20
                elif "бакалавр" in degree_lower or "bachelor" in degree_lower:
                    score += 10

        return min(score, 100)

    def _build_summary(self, profile: PersonProfile) -> str:
        """Построить текстовое резюме."""
        parts = []

        if profile.current_position and profile.current_company:
            parts.append(f"{profile.current_position} @ {profile.current_company}")

        if profile.experience:
            parts.append(f"{len(profile.experience)} мест работы")

        if profile.skills:
            parts.append(f"{len(profile.skills)} навыков")

        if profile.publications:
            total_citations = sum(p.citations or 0 for p in profile.publications)
            parts.append(f"{len(profile.publications)} публикаций ({total_citations} цитирований)")

        if profile.github:
            total_stars = sum(r.get("stars", 0) for r in profile.github.notable_repos)
            parts.append(f"{profile.github.public_repos} repos ({total_stars} stars)")

        if profile.red_flags:
            critical = sum(1 for rf in profile.red_flags if rf.priority == "CRITICAL")
            high = sum(1 for rf in profile.red_flags if rf.priority == "HIGH")
            if critical:
                parts.append(f"{critical} CRITICAL red flags")
            if high:
                parts.append(f"{high} HIGH red flags")

        return " | ".join(parts) if parts else "Нет данных"
