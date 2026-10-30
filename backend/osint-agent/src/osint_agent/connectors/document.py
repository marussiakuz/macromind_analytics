"""Document Connector — извлечение метаданных из документов.

Поддерживаемые форматы:
- PDF (pdfplumber)
- DOCX (python-docx)
- PPTX (python-pptx)
- XLSX (openpyxl)
- Изображения JPG/PNG (Pillow + EXIF)

Извлекает:
- Автор документа
- Дата создания/изменения
- Название/заголовок
- Организация
- Программа (creator/producer)
- Геолокация (из EXIF фото)
- Ключевые слова

ВАЖНО (152-ФЗ):
- Метаданные могут содержать персональные данные (имя автора)
- Изображения могут содержать геолокацию
- Все данные обрабатываются только для целей due diligence
- Path traversal защита: файлы только из разрешённых директорий
"""

import asyncio
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from osint_agent.connectors.base import BaseConnector
from osint_agent.models import ConnectorQuery, ConnectorResult, RedFlag, RedFlagCategory, RedFlagPriority
from osint_agent.utils import get_logger

logger = get_logger(__name__)

# Поддерживаемые форматы
SUPPORTED_FORMATS = {
    ".pdf": "extract_pdf_metadata",
    ".docx": "extract_docx_metadata",
    ".pptx": "extract_pptx_metadata",
    ".xlsx": "extract_xlsx_metadata",
    ".xls": "extract_xlsx_metadata",
    ".jpg": "extract_image_metadata",
    ".jpeg": "extract_image_metadata",
    ".png": "extract_image_metadata",
    ".gif": "extract_image_metadata",
    ".bmp": "extract_image_metadata",
}


class DocumentConnector(BaseConnector):
    """Извлечение метаданных из документов.

    Поддерживает: PDF, DOCX, PPTX, XLSX, JPG/PNG (EXIF)

    Извлекает:
    - author: автор документа
    - created: дата создания
    - modified: дата изменения
    - title: заголовок
    - organization: организация
    - creator: программа создания
    - producer: программа обработки
    - keywords: ключевые слова
    - geolocation: координаты (из EXIF фото)
    - pages: количество страниц (PDF)
    - slides: количество слайдов (PPTX)
    - text_preview: превью текста (первые 500 символов)
    """

    @property
    def name(self) -> str:
        return "document"

    @property
    def rate_limit(self) -> int:
        return 1000  # Локальные файлы — без ограничений

    async def fetch(self, query: ConnectorQuery) -> ConnectorResult:
        """Извлечь метаданные из документа.

        Args:
            query: ConnectorQuery с params:
                - file_path: str (путь к файлу)
                - extract_text: bool (извлекать ли текст, по умолчанию False)

        Returns:
            ConnectorResult с метаданными документа
        """
        file_path = query.params.get("file_path")
        extract_text = query.params.get("extract_text", False)

        if not file_path:
            return ConnectorResult(
                success=False,
                source=self.name,
                error="file_path is required",
            )

        # Валидация пути (path traversal защита)
        try:
            path = self._validate_path(file_path)
        except ValueError as e:
            return ConnectorResult(
                success=False,
                source=self.name,
                error=str(e),
            )

        # Проверяем существование файла
        if not path.exists():
            return ConnectorResult(
                success=False,
                source=self.name,
                error=f"File not found: {file_path}",
            )

        # Определяем формат
        ext = path.suffix.lower()
        if ext not in SUPPORTED_FORMATS:
            return ConnectorResult(
                success=False,
                source=self.name,
                error=f"Unsupported format: {ext}. Supported: {', '.join(SUPPORTED_FORMATS.keys())}",
            )

        try:
            # Извлекаем метаданные
            method_name = SUPPORTED_FORMATS[ext]
            method = getattr(self, method_name)
            metadata = await method(path)

            # Добавляем общую информацию
            metadata["file_path"] = str(path)
            metadata["file_name"] = path.name
            metadata["file_extension"] = ext
            metadata["file_size_bytes"] = path.stat().st_size

            # Извлекаем текст если запрошено
            if extract_text:
                text = await self._extract_text(path, ext)
                metadata["text_preview"] = text[:2000] if text else None
                metadata["text_length"] = len(text) if text else 0

            # Извлекаем email и телефоны из текста
            if extract_text and metadata.get("text_preview"):
                entities = self._extract_entities_from_text(metadata["text_preview"])
                metadata["emails_found"] = entities.get("emails", [])
                metadata["phones_found"] = entities.get("phones", [])

            return ConnectorResult(
                success=True,
                data=metadata,
                source=self.name,
                confidence=1.0,
            )

        except Exception as e:
            logger.error(
                "document_extract_error",
                file_path=file_path,
                error=str(e),
                exc_info=True,
            )
            return ConnectorResult(
                success=False,
                source=self.name,
                error=f"Failed to extract metadata: {str(e)}",
            )

    def _validate_path(self, file_path: str) -> Path:
        """Валидация пути к файлу (path traversal защита).

        Args:
            file_path: Путь к файлу

        Returns:
            Валидный Path объект

        Raises:
            ValueError: Если путь невалиден или выходит за пределы разрешённой директории
        """
        # Разрешённая директория (sandbox)
        allowed_dirs = [
            Path("data/uploads").resolve(),
            Path("data/documents").resolve(),
            Path("/tmp").resolve(),  # Для тестов
        ]

        path = Path(file_path).resolve()

        # Проверяем что путь находится в разрешённой директории
        is_allowed = False
        for allowed_dir in allowed_dirs:
            try:
                path.relative_to(allowed_dir)
                is_allowed = True
                break
            except ValueError:
                continue

        if not is_allowed:
            raise ValueError(f"Path {file_path} is outside allowed directories")

        # Проверяем что это не symlink
        if path.is_symlink():
            raise ValueError(f"Symlinks are not allowed: {file_path}")

        # Проверяем размер файла (максимум 100 MB)
        if path.exists() and path.stat().st_size > 100 * 1024 * 1024:
            raise ValueError(f"File too large (max 100 MB): {file_path}")

        return path

    async def extract_pdf_metadata(self, path: Path) -> dict[str, Any]:
        """Извлечь метаданные из PDF файла."""
        import pdfplumber

        with pdfplumber.open(path) as pdf:
            info = pdf.metadata or {}

            return {
                "format": "PDF",
                "author": info.get("Author"),
                "creator": info.get("Creator"),
                "producer": info.get("Producer"),
                "title": info.get("Title"),
                "subject": info.get("Subject"),
                "keywords": info.get("Keywords"),
                "created": self._parse_pdf_date(info.get("CreationDate")),
                "modified": self._parse_pdf_date(info.get("ModDate")),
                "pages": len(pdf.pages),
            }

    async def extract_docx_metadata(self, path: Path) -> dict[str, Any]:
        """Извлечь метаданные из Word документа."""
        from docx import Document

        doc = Document(path)
        props = doc.core_properties

        return {
            "format": "DOCX",
            "author": props.author,
            "last_modified_by": props.last_modified_by,
            "created": props.created.isoformat() if props.created else None,
            "modified": props.modified.isoformat() if props.modified else None,
            "title": props.title,
            "subject": props.subject,
            "keywords": props.keywords,
            "category": props.category,
            "comments": props.comments,
            "content_status": props.content_status,
            "language": props.language,
            "revision": props.revision,
            "version": props.version,
        }

    async def extract_pptx_metadata(self, path: Path) -> dict[str, Any]:
        """Извлечь метаданные из PowerPoint презентации."""
        from pptx import Presentation

        prs = Presentation(path)
        props = prs.core_properties

        # Подсчитываем количество слайдов с текстом
        slides_with_text = 0
        total_text_length = 0
        for slide in prs.slides:
            slide_text = []
            for shape in slide.shapes:
                if shape.has_text_frame:
                    for para in shape.text_frame.paragraphs:
                        text = para.text.strip()
                        if text:
                            slide_text.append(text)
            if slide_text:
                slides_with_text += 1
                total_text_length += sum(len(t) for t in slide_text)

        return {
            "format": "PPTX",
            "author": props.author,
            "last_modified_by": props.last_modified_by,
            "created": props.created.isoformat() if props.created else None,
            "modified": props.modified.isoformat() if props.modified else None,
            "title": props.title,
            "subject": props.subject,
            "keywords": props.keywords,
            "category": props.category,
            "comments": props.comments,
            "content_status": props.content_status,
            "language": props.language,
            "revision": props.revision,
            "version": props.version,
            "slides_count": len(prs.slides),
            "slides_with_text": slides_with_text,
            "total_text_length": total_text_length,
        }

    async def extract_xlsx_metadata(self, path: Path) -> dict[str, Any]:
        """Извлечь метаданные из Excel файла."""
        from openpyxl import load_workbook

        wb = load_workbook(path, read_only=True, data_only=True)
        props = wb.properties

        result = {
            "format": "XLSX",
            "author": props.creator if props else None,
            "last_modified_by": props.lastModifiedBy if props else None,
            "created": props.created.isoformat() if props and props.created else None,
            "modified": props.modified.isoformat() if props and props.modified else None,
            "title": props.title if props else None,
            "subject": props.subject if props else None,
            "description": props.description if props else None,
            "keywords": props.keywords if props else None,
            "category": props.category if props else None,
            "sheets": wb.sheetnames,
            "sheets_count": len(wb.sheetnames),
        }

        wb.close()
        return result

    async def extract_image_metadata(self, path: Path) -> dict[str, Any]:
        """Извлечь метаданные из изображения (EXIF)."""
        from PIL import Image
        from PIL.ExifTags import TAGS, GPSTAGS

        image = Image.open(path)

        result = {
            "format": image.format,
            "mode": image.mode,
            "width": image.size[0],
            "height": image.size[1],
        }

        # Извлекаем EXIF данные (публичный метод getexif())
        exif_data = image.getexif()
        if not exif_data:
            return result

        for tag_id, value in exif_data.items():
            tag = TAGS.get(tag_id, tag_id)

            # GPS данные
            if tag == "GPSInfo":
                gps_data = {}
                for gps_tag_id, gps_value in value.items():
                    gps_tag = GPSTAGS.get(gps_tag_id, gps_tag_id)
                    gps_data[gps_tag] = gps_value

                # Конвертировать в координаты
                if "GPSLatitude" in gps_data and "GPSLongitude" in gps_data:
                    try:
                        lat = self._convert_gps_coord(
                            gps_data["GPSLatitude"],
                            gps_data.get("GPSLatitudeRef", "N"),
                        )
                        lon = self._convert_gps_coord(
                            gps_data["GPSLongitude"],
                            gps_data.get("GPSLongitudeRef", "E"),
                        )
                        # Проверяем на нулевые координаты (Null Island)
                        if lat != 0.0 or lon != 0.0:
                            result["geolocation"] = {"latitude": lat, "longitude": lon}
                    except Exception:
                        pass
            else:
                # Сохраняем полезные EXIF теги
                if tag in [
                    "Make", "Model", "Software", "DateTime",
                    "DateTimeOriginal", "DateTimeDigitized",
                    "Artist", "Copyright", "ImageDescription",
                    "XPAuthor", "XPTitle", "XPComment",
                ]:
                    result[tag] = str(value) if value else None

        return result

    async def _extract_text(self, path: Path, ext: str) -> str:
        """Извлечь текст из документа."""
        try:
            if ext == ".pdf":
                import pdfplumber
                with pdfplumber.open(path) as pdf:
                    texts = []
                    for page in pdf.pages[:5]:  # Первые 5 страниц
                        text = page.extract_text()
                        if text:
                            texts.append(text)
                    return "\n".join(texts)

            elif ext == ".docx":
                from docx import Document
                doc = Document(path)
                texts = []
                for para in doc.paragraphs[:100]:  # Первые 100 параграфов
                    if para.text.strip():
                        texts.append(para.text)
                return "\n".join(texts)

            elif ext == ".pptx":
                from pptx import Presentation
                prs = Presentation(path)
                texts = []
                for slide in prs.slides[:20]:  # Первые 20 слайдов
                    for shape in slide.shapes:
                        if shape.has_text_frame:
                            for para in shape.text_frame.paragraphs:
                                text = para.text.strip()
                                if text:
                                    texts.append(text)
                return "\n".join(texts)

            elif ext in (".xlsx", ".xls"):
                from contextlib import closing
                from openpyxl import load_workbook
                with closing(load_workbook(path, read_only=True, data_only=True)) as wb:
                    texts = []
                    for sheet in wb.sheetnames[:3]:  # Первые 3 листа
                        ws = wb[sheet]
                        for row in ws.iter_rows(max_row=50, values_only=True):  # 50 строк
                            for cell in row:
                                if cell and isinstance(cell, str):
                                    texts.append(str(cell))
                    return "\n".join(texts)

        except Exception as e:
            logger.warning("text_extraction_error", file_path=str(path), error=str(e))

        return ""

    def _parse_pdf_date(self, date_str: str | None) -> str | None:
        """Парсинг даты из PDF метаданных.

        Формат PDF: D:20240115120000+03'00'
        """
        if not date_str:
            return None

        try:
            # Убираем D: в начале
            if date_str.startswith("D:"):
                date_str = date_str[2:]

            # Берем первые 14 символов (YYYYMMDDHHmmss)
            date_str = date_str[:14]

            # Парсим
            dt = datetime.strptime(date_str, "%Y%m%d%H%M%S")
            return dt.isoformat()
        except (ValueError, TypeError):
            return str(date_str)

    def _convert_gps_coord(self, coord: tuple, ref: str) -> float:
        """Конвертация GPS координат из EXIF формата в десятичные градусы."""
        d, m, s = coord
        decimal = d + m / 60 + s / 3600

        if ref in ("S", "W"):
            decimal = -decimal

        return round(decimal, 6)

    def _extract_entities_from_text(self, text: str) -> dict[str, list[str]]:
        """Извлечь email и телефоны из текста."""
        # Email паттерн
        emails = re.findall(r'[\w\.-]+@[\w\.-]+\.\w+', text)

        # Российские телефоны
        phones = re.findall(
            r'[\+]?[78][\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}',
            text,
        )

        return {
            "emails": list(set(emails)),
            "phones": list(set(phones)),
        }

    async def health_check(self) -> bool:
        """Проверка доступности (всегда True — локальные файлы)."""
        return True


class DocumentAnalyzer:
    """Анализ документов для выявления Red Flags."""

    def analyze(self, metadata: dict[str, Any]) -> list[RedFlag]:
        """Проанализировать метаданные документа."""
        from datetime import timezone

        red_flags = []

        # Проверка автора
        author = metadata.get("author")
        if author:
            # Проверяем на подозрительные имена
            suspicious_patterns = [
                "admin", "administrator", "user", "test",
                "temp", "default", "owner",
            ]
            if any(p in author.lower() for p in suspicious_patterns):
                red_flags.append(RedFlag(
                    id="DOC_SUSPICIOUS_AUTHOR",
                    priority=RedFlagPriority.LOW,
                    category=RedFlagCategory.REPUTATION,
                    description=f"Автор документа '{author}' — возможно стандартное имя",
                    block="D",
                    evidence={"author": author},
                    source_ref="Document metadata",
                ))

        # Проверка геолокации
        geolocation = metadata.get("geolocation")
        if geolocation:
            red_flags.append(RedFlag(
                id="DOC_GEOLOCATION_FOUND",
                priority=RedFlagPriority.MEDIUM,
                category=RedFlagCategory.REPUTATION,
                description="В метаданных изображения найдена геолокация",
                block="D",
                evidence={
                    "latitude": geolocation.get("latitude"),
                    "longitude": geolocation.get("longitude"),
                },
                source_ref="EXIF metadata",
            ))

        # Проверка устаревшего ПО
        creator = metadata.get("creator", "")
        if creator:
            old_software = [
                "Microsoft Word 2007", "Microsoft Word 2003",
                "Microsoft Excel 2007", "Microsoft Excel 2003",
                "OpenOffice.org", "LibreOffice 3", "LibreOffice 4",
            ]
            for sw in old_software:
                if sw.lower() in creator.lower():
                    red_flags.append(RedFlag(
                        id="DOC_OLD_SOFTWARE",
                        priority=RedFlagPriority.LOW,
                        category=RedFlagCategory.TECH,
                        description=f"Документ создан в устаревшем ПО: {creator}",
                        block="D",
                        evidence={"creator": creator},
                        source_ref="Document metadata",
                    ))
                    break

        # Проверка даты создания
        created = metadata.get("created")
        if created:
            try:
                created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                now = datetime.now(timezone.utc)

                # Документ из будущего
                if created_dt.replace(tzinfo=None) > now.replace(tzinfo=None):
                    red_flags.append(RedFlag(
                        id="DOC_FUTURE_DATE",
                        priority=RedFlagPriority.MEDIUM,
                        category=RedFlagCategory.REPUTATION,
                        description="Дата создания документа в будущем",
                        block="D",
                        evidence={"created": created},
                        source_ref="Document metadata",
                    ))
            except (ValueError, TypeError):
                pass

        # Проверка email в документе
        emails = metadata.get("emails_found", [])
        if emails:
            red_flags.append(RedFlag(
                id="DOC_EMAILS_FOUND",
                priority=RedFlagPriority.LOW,
                category=RedFlagCategory.REPUTATION,
                description=f"В документе найдены email-адреса: {', '.join(emails[:5])}",
                block="D",
                evidence={"emails": emails},
                source_ref="Document text",
            ))

        return red_flags


class MockDocumentConnector(BaseConnector):
    """Mock Document Connector для тестирования."""

    MOCK_DATA: dict[str, dict[str, Any]] = {
        "/path/to/pitch_deck.pdf": {
            "format": "PDF",
            "file_name": "pitch_deck.pdf",
            "file_extension": ".pdf",
            "file_size_bytes": 1048576,
            "author": "Иванов Петр Сергеевич",
            "creator": "Microsoft PowerPoint 2019",
            "producer": "Adobe PDF Library 15.0",
            "title": "ТехноСтарт — Pitch Deck",
            "created": "2024-01-15T10:30:00",
            "modified": "2024-01-20T14:45:00",
            "pages": 15,
            "is_encrypted": False,
        },
        "/path/to/contract.docx": {
            "format": "DOCX",
            "file_name": "contract.docx",
            "file_extension": ".docx",
            "file_size_bytes": 524288,
            "author": "Петров Алексей Викторович",
            "last_modified_by": "Сидорова Мария Ивановна",
            "created": "2024-02-01T09:00:00",
            "modified": "2024-02-05T16:30:00",
            "title": "Договор на оказание услуг",
            "subject": "Юридические услуги",
            "keywords": "договор, услуги, консалтинг",
        },
        "/path/to/financials.xlsx": {
            "format": "XLSX",
            "file_name": "financials.xlsx",
            "file_extension": ".xlsx",
            "file_size_bytes": 262144,
            "author": "Бухгалтер Анна",
            "last_modified_by": "CFO John Smith",
            "created": "2024-03-01T12:00:00",
            "modified": "2024-03-15T18:00:00",
            "title": "Финансовая отчетность 2023",
            "sheets": ["Баланс", "P&L", "Cash Flow"],
            "sheets_count": 3,
        },
        "/path/to/photo.jpg": {
            "format": "JPEG",
            "file_name": "photo.jpg",
            "file_extension": ".jpg",
            "file_size_bytes": 2097152,
            "width": 4032,
            "height": 3024,
            "Make": "Apple",
            "Model": "iPhone 14 Pro",
            "Software": "16.2",
            "DateTimeOriginal": "2024:01:15 10:30:00",
            "geolocation": {"latitude": 55.7558, "longitude": 37.6173},
        },
        "/path/to/presentation.pptx": {
            "format": "PPTX",
            "file_name": "presentation.pptx",
            "file_extension": ".pptx",
            "file_size_bytes": 5242880,
            "author": "Иванов Петр Сергеевич",
            "last_modified_by": "Иванов Петр Сергеевич",
            "created": "2024-06-01T10:00:00",
            "modified": "2024-06-15T18:30:00",
            "title": "MacroMind Analytics — Pitch Deck",
            "subject": "Инвестиционная презентация",
            "keywords": "стартап, инвестиции, AI, OSINT",
            "slides_count": 18,
            "slides_with_text": 15,
            "total_text_length": 4500,
        },
    }

    @property
    def name(self) -> str:
        return "document"

    @property
    def rate_limit(self) -> int:
        return 1000

    async def fetch(self, query: ConnectorQuery) -> ConnectorResult:
        """Вернуть mock данные документа."""
        file_path = query.params.get("file_path")

        if not file_path:
            return ConnectorResult(
                success=False,
                source=self.name,
                error="file_path is required",
            )

        await asyncio.sleep(0.05)

        # Ищем по имени файла
        for key, data in self.MOCK_DATA.items():
            if Path(key).name == Path(file_path).name or key == file_path:
                return ConnectorResult(
                    success=True,
                    data=data,
                    source=f"{self.name}:mock",
                )

        # Если не нашли — возвращаем базовые данные
        return ConnectorResult(
            success=True,
            data={
                "format": "UNKNOWN",
                "file_name": Path(file_path).name,
                "file_extension": Path(file_path).suffix,
                "file_size_bytes": 0,
                "author": "Unknown",
            },
            source=f"{self.name}:mock",
        )

    async def health_check(self) -> bool:
        return True
