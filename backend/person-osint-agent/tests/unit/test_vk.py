"""Tests for VK connector and Name Variations."""

import pytest
from person_osint.connectors.vk import MockVKConnector
from person_osint.models import ConnectorQuery
from person_osint.name_variations import (
    generate_transliterations,
    generate_diminutives,
    generate_name_variants,
    detect_kazakh_patronymic,
)


@pytest.fixture
def vk():
    return MockVKConnector()


@pytest.mark.unit
class TestMockVKConnector:
    """Tests for MockVKConnector."""

    def test_name(self, vk):
        assert vk.name == "vk"

    @pytest.mark.asyncio
    async def test_search(self, vk):
        result = await vk.fetch(
            ConnectorQuery(query_type="vk", params={"action": "search", "full_name": "Иванов Иван Иванович"})
        )
        assert result.success
        assert result.data["found"] is True
        assert len(result.data["users"]) == 2

    @pytest.mark.asyncio
    async def test_search_unknown(self, vk):
        result = await vk.fetch(
            ConnectorQuery(query_type="vk", params={"action": "search", "full_name": "Неизвестный"})
        )
        assert result.success
        assert result.data["found"] is False

    @pytest.mark.asyncio
    async def test_mutual_friends(self, vk):
        result = await vk.fetch(
            ConnectorQuery(query_type="vk", params={"action": "mutual_friends", "source_uid": 1, "target_uid": 2})
        )
        assert result.success
        assert result.data["mutual_friends_count"] == 5


@pytest.mark.unit
class TestTransliterations:
    """Tests for name transliteration."""

    def test_cyrillic_to_latin(self):
        result = generate_transliterations("Иванов")
        assert "Иванов" in result
        assert any("ivanov" in r.lower() for r in result)

    def test_latin_to_cyrillic(self):
        result = generate_transliterations("Ivanov")
        assert "Ivanov" in result
        assert any("иванов" in r.lower() for r in result)

    def test_short_name(self):
        result = generate_transliterations("И")
        assert "И" in result


@pytest.mark.unit
class TestDiminutives:
    """Tests for diminutive forms."""

    def test_ivan_to_vanya(self):
        result = generate_diminutives("Иван")
        assert "иван" in result
        assert "ваня" in result
        assert "ванька" in result

    def test_dmitry_to_dima(self):
        result = generate_diminutives("Дмитрий")
        assert "дмитрий" in result
        assert "дима" in result

    def test_alexandra_to_sasha(self):
        result = generate_diminutives("Александра")
        assert "саша" in result

    def test_unknown_name(self):
        result = generate_diminutives("Ксзрф")
        assert result == []


@pytest.mark.unit
class TestNameVariants:
    """Tests for full name variant generation."""

    def test_full_name(self):
        variants = generate_name_variants("Иванов Иван Иванович")
        assert "Иванов Иван Иванович" in variants
        # Должны быть перестановки
        assert any("Иван" in v and "Иванов" in v for v in variants)

    def test_two_part_name(self):
        variants = generate_name_variants("Иванов Иван")
        assert "Иванов Иван" in variants
        assert "Иван Иванов" in variants

    def test_single_name(self):
        variants = generate_name_variants("Иванов")
        assert "Иванов" in variants

    def test_no_duplicates(self):
        variants = generate_name_variants("Иванов Иван Иванович")
        assert len(variants) == len(set(variants))


@pytest.mark.unit
class TestKazakhPatronymic:
    """Tests for Kazakh patronymic detection (OSINT F.5)."""

    def test_kazakh_male(self):
        result = detect_kazakh_patronymic("Сериков Арман Нурланулы")
        assert result is not None
        assert result["is_kazakh"] is True
        assert "нурлан" in result["father_name"]

    def test_kazakh_female(self):
        result = detect_kazakh_patronymic("Ахметова Айгуль Еркинкызы")
        assert result is not None
        assert result["is_kazakh"] is True

    def test_not_kazakh(self):
        result = detect_kazakh_patronymic("Иванов Иван Иванович")
        assert result is None

    def test_two_part_name(self):
        result = detect_kazakh_patronymic("Иванов Иван")
        assert result is None
