"""Username Scanner — сканер по никнеймам.

Адаптировано из social-analyzer (данные, не код).
Ищет профили по username на 999+ сайтах.
"""

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import httpx

from person_osint.connectors.base import BaseConnector
from person_osint.models import ConnectorQuery, ConnectorResult


DATA_DIR = Path(__file__).parent.parent / "data"


class UsernameScanner:
    """Сканер по никнеймам на множестве сайтов."""

    def __init__(self, sites_path: Path | None = None):
        self.sites_path = sites_path or DATA_DIR / "sites.json"
        self.sites: list[dict] = []
        self._load_sites()

    def _load_sites(self):
        """Загрузить список сайтов."""
        if self.sites_path.exists():
            with open(self.sites_path, encoding="utf-8") as f:
                data = json.load(f)
                self.sites = data.get("websites_entries", [])

    def scan(self, username: str, max_workers: int = 15, max_sites: int = 100) -> list[dict[str, Any]]:
        """Сканировать username на множестве сайтов.

        Args:
            username: Логин для поиска
            max_workers: Количество параллельных потоков
            max_sites: Максимум сайтов для проверки

        Returns:
            Список найденных профилей
        """
        # Фильтруем выбранные сайты
        selected = [s for s in self.sites if s.get("selected") == "true"][:max_sites]

        if not selected:
            selected = self.sites[:max_sites]

        results = []
        failed = []

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(self._check_site, username, site): site
                for site in selected
            }

            for future in as_completed(futures):
                site = futures[future]
                try:
                    result = future.result(timeout=10)
                    if result:
                        results.append(result)
                except Exception:
                    failed.append(site.get("url", ""))

        # Retry failed (1 раз)
        if failed:
            retry_sites = [s for s in selected if s.get("url", "") in failed]
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {
                    executor.submit(self._check_site, username, site): site
                    for site in retry_sites[:20]
                }
                for future in as_completed(futures):
                    try:
                        result = future.result(timeout=10)
                        if result:
                            results.append(result)
                    except Exception:
                        pass

        # Сортируем по rate
        results.sort(key=lambda x: x.get("rate", 0), reverse=True)
        return results

    def _check_site(self, username: str, site: dict) -> dict[str, Any] | None:
        """Проверить один сайт."""
        url_template = site.get("url", "")
        if not url_template:
            return None

        url = url_template.replace("{username}", username)
        detections = site.get("detections", [])

        if not detections:
            return None

        try:
            with httpx.Client(timeout=5.0, follow_redirects=True) as client:
                response = client.get(url, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                })

                if response.status_code != 200:
                    return None

                source = response.text

                # Проверяем детекции
                found_count = 0
                total_count = len(detections)

                for detection in detections:
                    det_type = detection.get("type", "normal")
                    det_string = detection.get("string", "").replace("{username}", username)
                    det_return = detection.get("return", "true")

                    if det_type == "normal":
                        # Проверяем в HTML
                        detected = det_string.lower() in source.lower()
                    elif det_type == "advanced":
                        # Проверяем в тексте (упрощённо)
                        from bs4 import BeautifulSoup
                        soup = BeautifulSoup(source, "lxml")
                        text = soup.get_text()
                        detected = det_string.lower() in text.lower()
                    else:
                        continue

                    if detected and det_return == "true":
                        found_count += 1
                    elif not detected and det_return == "false":
                        found_count += 1

                if total_count == 0:
                    return None

                rate = (found_count / total_count) * 100

                if rate < 50:
                    return None

                # Определяем статус
                if rate >= 100:
                    status = "good"
                elif rate >= 50:
                    status = "maybe"
                else:
                    status = "bad"

                return {
                    "url": url,
                    "site": self._extract_domain(url_template),
                    "username": username,
                    "rate": rate,
                    "status": status,
                    "found": found_count,
                    "total": total_count,
                    "type": site.get("type", ""),
                    "country": site.get("country", ""),
                    "nsfw": site.get("nsfw", "false") == "true",
                    "source": "username_scan",
                }

        except Exception:
            return None

    def _extract_domain(self, url: str) -> str:
        """Извлечь домен из URL template."""
        url = url.replace("{username}", "test")
        try:
            from urllib.parse import urlparse
            return urlparse(url).netloc
        except Exception:
            return url


class UsernameScanConnector(BaseConnector):
    """Connector для сканирования по никнеймам."""

    def __init__(self):
        super().__init__()
        self.scanner = UsernameScanner()

    @property
    def name(self) -> str:
        return "username_scan"

    @property
    def rate_limit(self) -> int:
        return 1000

    async def fetch(self, query: ConnectorQuery) -> ConnectorResult:
        """Сканировать username."""
        username = query.params.get("username")
        if not username:
            return ConnectorResult(
                success=False,
                source=self.name,
                error="username is required",
            )

        max_sites = query.params.get("max_sites", 50)

        # Запускаем в thread pool (сканер синхронный)
        import asyncio
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(
            None, lambda: self.scanner.scan(username, max_sites=max_sites)
        )

        return ConnectorResult(
            success=True,
            data={
                "found": len(results) > 0,
                "username": username,
                "total_checked": max_sites,
                "found_count": len(results),
                "profiles": results,
            },
            source=self.name,
            confidence=0.8,
        )

    async def health_check(self) -> bool:
        return True


class MockUsernameScanConnector(BaseConnector):
    """Mock username scan connector."""

    @property
    def name(self) -> str:
        return "username_scan"

    @property
    def rate_limit(self) -> int:
        return 1000

    async def fetch(self, query: ConnectorQuery) -> ConnectorResult:
        """Вернуть mock данные."""
        import asyncio
        await asyncio.sleep(0.05)

        username = query.params.get("username", "")

        return ConnectorResult(
            success=True,
            data={
                "found": True,
                "username": username,
                "total_checked": 50,
                "found_count": 3,
                "profiles": [
                    {
                        "url": f"https://github.com/{username}",
                        "site": "github.com",
                        "username": username,
                        "rate": 100,
                        "status": "good",
                        "source": "username_scan",
                    },
                    {
                        "url": f"https://twitter.com/{username}",
                        "site": "twitter.com",
                        "username": username,
                        "rate": 85,
                        "status": "maybe",
                        "source": "username_scan",
                    },
                ],
            },
            source=f"{self.name}:mock",
        )

    async def health_check(self) -> bool:
        return True
