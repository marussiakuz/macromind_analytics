"""Name Variations — генерация вариаций ФИО для поиска.

Из OSINT_Rules.md:
- F.2: Транслитерация кириллица ↔ латиница
- F.2.1: Уменьшительные формы, разные написания
- F.5: Казахские ФИО — патронимическая система
"""

import re
from typing import Any


# Транслитерация кириллица → латиница
CYR_TO_LAT = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'e',
    'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
    'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
    'ф': 'f', 'х': 'kh', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'shch',
    'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya',
}

LAT_TO_CYR = {
    'a': 'а', 'b': 'б', 'v': 'в', 'g': 'г', 'd': 'д', 'e': 'е', 'z': 'з',
    'i': 'и', 'y': 'й', 'k': 'к', 'l': 'л', 'm': 'м', 'n': 'н', 'o': 'о',
    'p': 'п', 'r': 'р', 's': 'с', 't': 'т', 'u': 'у', 'f': 'ф', 'h': 'х',
    'c': 'ц', 'x': 'кс',
}

# Уменьшительные формы имён
DIMINUTIVE_FORMS: dict[str, list[str]] = {
    'александр': ['саша', 'шура', 'алекс', 'санёк', 'шурик'],
    'алексей': ['лёша', 'алёша', 'лёха', 'алекс'],
    'андрей': ['андрюша', 'андрюха'],
    'антон': ['антоша', 'антоха'],
    'артём': ['тема', 'артёмка'],
    'борис': ['боря', 'борька'],
    'вадим': ['вадик'],
    'валентин': ['валя', 'валик'],
    'василий': ['вася', 'васька'],
    'виктор': ['витя', 'витёк'],
    'виталий': ['виталик'],
    'владимир': ['вова', 'володя', 'вовка'],
    'владислав': ['влад', 'владик'],
    'вячеслав': ['слава', 'славик'],
    'геннадий': ['гена', 'генка'],
    'георгий': ['жора', 'гоша'],
    'григорий': ['гриша', 'гришка'],
    'даниил': ['даня', 'даник'],
    'дмитрий': ['дима', 'митя', 'димка'],
    'евгений': ['женя', 'женёк'],
    'егор': ['егорка'],
    'иван': ['ваня', 'ванька'],
    'игорь': ['игорёк'],
    'илья': ['ильюша'],
    'кирилл': ['кирик', 'кирюша'],
    'константин': ['костя', 'костик'],
    'леонид': ['лёня', 'лёник'],
    'максим': ['макс', 'максимка'],
    'михаил': ['миша', 'мишка'],
    'николай': ['коля', 'колька'],
    'олег': ['олежка'],
    'павел': ['паша', 'пашка'],
    'пётр': ['петя', 'петька'],
    'роман': ['рома', 'ромка'],
    'сергей': ['серёжа', 'серый'],
    'станислав': ['стас', 'стасик'],
    'степан': ['стёпа', 'стёпка'],
    'тимофей': ['тима', 'тимоша'],
    'фёдор': ['федя', 'федька'],
    'юрий': ['юра', 'юрка'],
    'ярослав': ['ярик', 'слава'],

    # Женские
    'александра': ['саша', 'шура', 'сашка'],
    'алла': ['аллочка'],
    'анастасия': ['настя', 'настюша', 'настася'],
    'анна': ['аня', 'анька', 'анюта'],
    'валентина': ['валя', 'валик'],
    'вера': ['верочка'],
    'виктория': ['вика', 'викочка'],
    'галина': ['галя', 'галька'],
    'дарья': ['даша', 'дашка'],
    'екатерина': ['катя', 'катюша', 'катенька'],
    'елена': ['лена', 'леночка', 'ленка'],
    'елизавета': ['лиза', 'лизка', 'лизавета'],
    'ирина': ['ира', 'ирочка'],
    'ксения': ['ксюша', 'ксюха'],
    'лариса': ['лара', 'ларочка'],
    'людмила': ['люда', 'людочка'],
    'маргарита': ['рита', 'риточка'],
    'мария': ['маша', 'машка', 'маня'],
    'надежда': ['надя', 'надька'],
    'наталья': ['наташа', 'наташка'],
    'нина': ['ниночка'],
    'оксана': ['оксаночка'],
    'ольга': ['оля', 'олька'],
    'полина': ['поля', 'полька'],
    'светлана': ['света', 'светка'],
    'софия': ['соня', 'сонька'],
    'тамара': ['тома', 'тамарочка'],
    'татьяна': ['таня', 'танька'],
    'юлия': ['юля', 'юлька'],
    'яна': ['яночка'],
}

# Сокращения фамилий (инициалы)
INITIAL_PATTERNS = [
    r'^([А-ЯЁа-яё])\.\s*([А-ЯЁа-яё])\.\s*(.+)$',  # И.И. Иванов
    r'^(.+)\s+([А-ЯЁа-яё])\.\s*([А-ЯЁа-яё])\.$',  # Иванов И.И.
    r'^([A-Za-z])\.\s*([A-Za-z])\.\s*(.+)$',  # I.I. Ivanov
    r'^(.+)\s+([A-Za-z])\.\s*([A-Za-z])\.$',  # Ivanov I.I.
]


def generate_transliterations(name: str) -> list[str]:
    """Генерация транслитераций имени (кириллица ↔ латиница).

    OSINT F.2: транслитерация ФИО в обоих направлениях.
    """
    result = [name]
    name_lower = name.lower()

    # Определяем направление
    is_cyrillic = bool(re.search(r'[а-яё]', name_lower))

    if is_cyrillic:
        # Кириллица → латиница
        latin = ''
        for char in name_lower:
            latin += CYR_TO_LAT.get(char, char)
        result.append(latin)

        # Вариант с заглавной буквой
        result.append(latin.capitalize())

        # Разные стандарты транслитерации
        # ISO 9
        iso = name_lower
        for cyr, lat in CYR_TO_LAT.items():
            iso = iso.replace(cyr, lat)
        result.append(iso.capitalize())
    else:
        # Латиница → кириллица
        cyrillic = ''
        i = 0
        while i < len(name_lower):
            # Проверяем двухбуквенные комбинации
            if i + 1 < len(name_lower):
                pair = name_lower[i:i+2]
                if pair in ('zh', 'kh', 'ts', 'ch', 'sh', 'yu', 'ya'):
                    cyrillic += LAT_TO_CYR.get(pair[0], pair[0])
                    i += 2
                    continue
            cyrillic += LAT_TO_CYR.get(name_lower[i], name_lower[i])
            i += 1
        result.append(cyrillic)

    return list(set(result))


def generate_diminutives(name: str) -> list[str]:
    """Генерация уменьшительных форм имени.

    OSINT F.2.1: сокращённые и уменьшительно-ласкательные формы.
    """
    result = []
    name_lower = name.lower().strip()

    # Ищем в словаре
    for full_form, diminutives in DIMINUTIVE_FORMS.items():
        if name_lower == full_form or name_lower in diminutives:
            result.append(full_form)
            result.extend(diminutives)
            break

    return list(set(result))


def generate_name_variants(full_name: str) -> list[str]:
    """Генерация всех вариаций ФИО для поиска.

    OSINT F.2: полный набор вариаций.
    """
    variants = [full_name]

    # Разбиваем на части
    parts = full_name.strip().split()
    if len(parts) < 2:
        return variants

    # Транслитерация всего имени
    variants.extend(generate_transliterations(full_name))

    # Для каждого компонента
    for part in parts:
        variants.extend(generate_transliterations(part))
        variants.extend(generate_diminutives(part))

    # Перестановки (фамилия имя отчество → имя фамилия отчество)
    if len(parts) >= 3:
        variants.append(f"{parts[1]} {parts[0]} {parts[2]}")
        variants.append(f"{parts[1]} {parts[2]} {parts[0]}")
        variants.append(f"{parts[0]} {parts[2]} {parts[1]}")

    if len(parts) == 2:
        variants.append(f"{parts[1]} {parts[0]}")

    # Без отчества
    if len(parts) >= 3:
        variants.append(f"{parts[0]} {parts[1]}")

    # Инициалы
    if len(parts) >= 3:
        variants.append(f"{parts[0][0]}.{parts[2][0]}. {parts[1]}")  # И.И. Иванов
        variants.append(f"{parts[1]} {parts[0][0]}.{parts[2][0]}.")  # Иванов И.И.

    # Очистка и дедупликация
    cleaned = []
    for v in variants:
        v = v.strip()
        if v and v not in cleaned:
            cleaned.append(v)

    return cleaned


def detect_kazakh_patronymic(full_name: str) -> dict[str, Any] | None:
    """Определить казахское отчество (OSINT F.5).

    Патронимическая система — отчество и фамилия производятся от имени отца/деда.
    """
    parts = full_name.strip().split()
    if len(parts) < 3:
        return None

    # Проверяем типичные суффиксы казахских отчеств
    patronymic = parts[2] if len(parts) >= 3 else None
    surname = parts[0]

    # Казахские отчества: -ович/-евич (м), -овна/-евна (ж)
    # Казахские фамилии часто заканчиваются на -ов/-ев/-овна
    kazakh_suffixes = ['улы', 'уулы', 'кызы', 'қызы', 'ұлы']

    if patronymic:
        patronymic_lower = patronymic.lower()
        for suffix in kazakh_suffixes:
            if patronymic_lower.endswith(suffix):
                # Извлекаем имя отца
                father_name = patronymic_lower[:-len(suffix)]
                return {
                    "is_kazakh": True,
                    "patronymic": patronymic,
                    "father_name": father_name,
                    "search_hint": f"Search also for: {father_name}",
                }

    return None
