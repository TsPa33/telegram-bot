from __future__ import annotations

import csv
import hashlib
import io
import re
import zipfile
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any
from xml.etree import ElementTree as ET

from bot.database.repositories.seller_repo import get_or_create_seller
from bot.database.repositories.model_repo import get_model_id
from bot.database.repositories.product_repo import create_product, get_product_by_title_oem
from bot.database.base import execute


# ================= SELLER IMPORT PARSER (legacy) =================

async def parse_seller_file(text: str):
    rows = []

    for line_no, line in enumerate(text.splitlines(), start=1):
        line = line.strip()

        if not line:
            continue

        parts = [p.strip() for p in line.split("|")]

        # очікуємо рівно 6 колонок
        if len(parts) != 6:
            continue

        shop_name, website, phone, name, brand, model = parts

        rows.append({
            "shop_name": shop_name,
            "website": website,
            "phone": phone,
            "name": name,
            "brand": brand,
            "model": model,
            "_line_no": line_no
        })

    return rows


# ================= SELLER IMPORT SAVE (legacy) =================

def _normalize_phone(phone: str) -> str:
    value = (phone or "").strip()
    digits = re.sub(r"[^\d+]", "", value)
    return digits or value


def _stable_telegram_id_from_phone(phone: str) -> int:
    normalized = _normalize_phone(phone)
    digest = hashlib.blake2b(normalized.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, byteorder="big", signed=False)


async def save_parsed_data(rows: list[dict]):
    inserted_rows = 0
    unique_pairs: set[tuple[int, int]] = set()

    for row in rows:
        try:
            print("ROW:", row)

            # ================= SELLER =================
            # унікальність через phone
            telegram_id = _stable_telegram_id_from_phone(row["phone"])

            seller = await get_or_create_seller(
                telegram_id=telegram_id,
                username=None
            )
            print("SELLER:", row["phone"], seller["id"])

            # оновлюємо профіль
            await execute("""
                UPDATE sellers
                SET
                    shop_name = $1,
                    website = $2,
                    phone = $3,
                    name = $4
                WHERE id = $5
            """,
            row["shop_name"],
            row["website"],
            row["phone"],
            row["name"],
            seller["id"]
            )

            # ================= MODEL =================
            model_id = await get_model_id(
                row["brand"],
                row["model"]
            )
            print("MODEL:", row["brand"], row["model"], model_id)

            if not model_id:
                continue

            # ================= INSERT =================
            print("INSERT:", seller["id"], model_id)
            unique_pairs.add((seller["id"], model_id))

            await execute("""
                INSERT INTO seller_cars (
                    seller_id,
                    model_id,
                    photo_id,
                    description
                )
                VALUES ($1, $2, NULL, '')
            """,
            seller["id"],
            model_id
            )
            inserted_rows += 1

        except Exception as e:
            # щоб імпорт не падав повністю
            print(f"IMPORT ERROR: {e}")
            continue

    print(f"Imported {inserted_rows} seller_cars rows")
    print(f"Unique (seller_id, model_id) pairs: {len(unique_pairs)}")
    return inserted_rows


# ================= PRODUCT IMPORT =================

PRODUCT_IMPORT_COLUMNS = [
    "title",
    "category",
    "brand",
    "model",
    "oem_code",
    "condition",
    "price",
    "quantity",
    "stock_status",
    "description",
]

PRODUCT_IMPORT_EXAMPLE_ROW = {
    "title": "Фара передня ліва",
    "category": "Оптика",
    "brand": "Volkswagen",
    "model": "Golf VII",
    "oem_code": "5G1941005",
    "condition": "used",
    "price": "3200",
    "quantity": "2",
    "stock_status": "available",
    "description": "Оригінальна фара з донорського авто, без тріщин.",
}

STOCK_STATUS_ALIASES = {
    "available": "available",
    "in_stock": "available",
    "instock": "available",
    "in stock": "available",
    "є": "available",
    "так": "available",
    "наявний": "available",
    "наявна": "available",
    "в наявності": "available",
    "low_stock": "low_stock",
    "low stock": "low_stock",
    "low": "low_stock",
    "мало": "low_stock",
    "мало в наявності": "low_stock",
    "sold": "sold",
    "out_of_stock": "sold",
    "out of stock": "sold",
    "немає": "sold",
    "нема": "sold",
    "продано": "sold",
    "0": "sold",
    "preorder": "preorder",
    "pre-order": "preorder",
    "pre order": "preorder",
    "передзамовлення": "preorder",
    "під замовлення": "preorder",
}


@dataclass
class ProductImportRowError:
    row_number: int
    values: dict[str, str]
    errors: list[str]


@dataclass
class ProductImportResult:
    imported_count: int = 0
    skipped_count: int = 0
    failed_rows: list[ProductImportRowError] = field(default_factory=list)
    validation_errors: list[str] = field(default_factory=list)

    @property
    def failed_count(self) -> int:
        return len(self.failed_rows)


def generate_product_import_csv_template() -> bytes:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=PRODUCT_IMPORT_COLUMNS)
    writer.writeheader()
    writer.writerow(PRODUCT_IMPORT_EXAMPLE_ROW)
    return output.getvalue().encode("utf-8-sig")


def generate_product_import_xlsx_template() -> bytes:
    rows = [PRODUCT_IMPORT_COLUMNS, [PRODUCT_IMPORT_EXAMPLE_ROW[column] for column in PRODUCT_IMPORT_COLUMNS]]
    return _build_simple_xlsx(rows)


async def import_products_from_file(*, seller_id: int, filename: str, content: bytes) -> ProductImportResult:
    result = ProductImportResult()
    try:
        parsed_rows = parse_product_import_file(filename=filename, content=content)
    except ValueError as exc:
        result.validation_errors.append(str(exc))
        return result

    seen_in_file: set[tuple[str, str]] = set()
    for row_number, raw_row in parsed_rows:
        values = _trim_row(raw_row)
        if _is_empty_row(values):
            result.skipped_count += 1
            continue

        payload, errors = _validate_product_row(values)
        duplicate_key = _duplicate_key(values)
        if duplicate_key and duplicate_key in seen_in_file:
            result.skipped_count += 1
            continue
        if errors:
            result.failed_rows.append(ProductImportRowError(row_number=row_number, values=values, errors=errors))
            continue

        if duplicate_key:
            seen_in_file.add(duplicate_key)
            existing = await get_product_by_title_oem(
                seller_id=seller_id,
                title=payload["title"],
                oem_code=payload.get("oem_code"),
            )
            if existing:
                result.skipped_count += 1
                continue

        try:
            created = await create_product(seller_id=seller_id, **payload)
        except Exception as exc:  # keep partial import safe if one row fails at DB layer
            result.failed_rows.append(
                ProductImportRowError(row_number=row_number, values=values, errors=[f"Не вдалося зберегти рядок: {exc}"])
            )
            continue
        if created:
            result.imported_count += 1
        else:
            result.failed_rows.append(
                ProductImportRowError(row_number=row_number, values=values, errors=["Не вдалося зберегти товар."])
            )
    return result


def parse_product_import_file(*, filename: str, content: bytes) -> list[tuple[int, dict[str, Any]]]:
    lower_name = (filename or "").lower()
    if lower_name.endswith(".csv"):
        return _parse_product_csv(content)
    if lower_name.endswith(".xlsx"):
        return _parse_product_xlsx(content)
    raise ValueError("Підтримуються лише CSV або XLSX файли.")


def _parse_product_csv(content: bytes) -> list[tuple[int, dict[str, Any]]]:
    text = content.decode("utf-8-sig")
    sample = text[:2048]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t") if sample.strip() else csv.excel
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    headers = reader.fieldnames or []
    _validate_headers(headers)
    normalized_headers = {header: _normalize_header(header) for header in headers}
    parsed = []
    for index, row in enumerate(reader, start=2):
        parsed.append((index, {normalized_headers.get(header, header): value for header, value in row.items()}))
    return parsed


def _parse_product_xlsx(content: bytes) -> list[tuple[int, dict[str, Any]]]:
    rows = _read_simple_xlsx_rows(content)
    if not rows:
        raise ValueError("Файл не містить рядків.")
    headers = [str(value or "").strip() for value in rows[0]]
    _validate_headers(headers)
    normalized_headers = [_normalize_header(header) for header in headers]
    parsed = []
    for excel_row_number, row in enumerate(rows[1:], start=2):
        parsed.append((excel_row_number, {header: row[index] if index < len(row) else "" for index, header in enumerate(normalized_headers)}))
    return parsed


def _validate_headers(headers: list[str]) -> None:
    normalized = {_normalize_header(header) for header in headers if str(header or "").strip()}
    missing = [column for column in PRODUCT_IMPORT_COLUMNS if column not in normalized]
    if missing:
        raise ValueError("У файлі відсутні колонки: " + ", ".join(missing))


def _normalize_header(value: str) -> str:
    return str(value or "").strip().lower().replace(" ", "_")


def _trim_row(row: dict[str, Any]) -> dict[str, str]:
    trimmed = {}
    for column in PRODUCT_IMPORT_COLUMNS:
        value = row.get(column, "")
        if value is None:
            value = ""
        trimmed[column] = str(value).strip()
    return trimmed


def _is_empty_row(row: dict[str, str]) -> bool:
    return not any(value for value in row.values())


def _validate_product_row(row: dict[str, str]) -> tuple[dict[str, Any], list[str]]:
    errors = []
    title = row["title"]
    category = row["category"]
    if not title:
        errors.append("title обов’язковий")
    if not category:
        errors.append("category обов’язкова")

    price, price_error = _parse_price(row["price"])
    if price_error:
        errors.append(price_error)
    quantity, quantity_error = _parse_quantity(row["quantity"])
    if quantity_error:
        errors.append(quantity_error)
    stock_status, stock_error = _parse_stock_status(row["stock_status"])
    if stock_error:
        errors.append(stock_error)

    payload = {
        "title": title,
        "category": category,
        "brand": row["brand"] or None,
        "model": row["model"] or None,
        "oem_code": row["oem_code"] or None,
        "condition": row["condition"] or None,
        "description": row["description"] or None,
        "price": price,
        "quantity": quantity,
        "stock_status": stock_status,
        "status": "active",
    }
    return payload, errors


def _parse_price(value: str) -> tuple[Decimal | None, str | None]:
    raw = (value or "").strip().replace(" ", "").replace(",", ".")
    if not raw:
        return None, None
    try:
        price = Decimal(raw)
    except InvalidOperation:
        return None, "price має бути числом"
    if price < 0:
        return None, "price не може бути від’ємною"
    if price > Decimal("100000000"):
        return None, "price занадто велика"
    return price.quantize(Decimal("0.01")), None


def _parse_quantity(value: str) -> tuple[int, str | None]:
    raw = (value or "").strip()
    if not raw:
        return 1, None
    try:
        quantity_decimal = Decimal(raw.replace(",", "."))
    except (InvalidOperation, ValueError):
        return 1, "quantity має бути цілим числом"
    if quantity_decimal != quantity_decimal.to_integral_value():
        return 1, "quantity має бути цілим числом"
    quantity = int(quantity_decimal)
    if quantity < 0:
        return 1, "quantity не може бути від’ємною"
    if quantity > 1_000_000:
        return 1, "quantity занадто велика"
    return quantity, None


def _parse_stock_status(value: str) -> tuple[str, str | None]:
    raw = (value or "").strip().lower()
    if not raw:
        return "available", None
    stock_status = STOCK_STATUS_ALIASES.get(raw)
    if not stock_status:
        return "available", "stock_status має бути available, low_stock, sold або preorder"
    return stock_status, None


def _duplicate_key(row: dict[str, str]) -> tuple[str, str] | None:
    title = row.get("title", "").strip().casefold()
    oem_code = row.get("oem_code", "").strip().casefold()
    if not title or not oem_code:
        return None
    return title, oem_code


def _read_simple_xlsx_rows(content: bytes) -> list[list[str]]:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            shared_strings = _read_shared_strings(archive)
            sheet_name = _first_sheet_name(archive)
            sheet_xml = archive.read(sheet_name)
    except (KeyError, zipfile.BadZipFile) as exc:
        raise ValueError("Не вдалося прочитати XLSX файл.") from exc

    root = ET.fromstring(sheet_xml)
    namespace = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    rows = []
    for row_node in root.findall(".//x:sheetData/x:row", namespace):
        row_values: list[str] = []
        for cell in row_node.findall("x:c", namespace):
            cell_ref = cell.attrib.get("r", "")
            column_index = _cell_column_index(cell_ref)
            while len(row_values) <= column_index:
                row_values.append("")
            row_values[column_index] = _cell_text(cell, shared_strings, namespace)
        rows.append(row_values)
    return rows


def _read_shared_strings(archive: zipfile.ZipFile) -> list[str]:
    try:
        xml = archive.read("xl/sharedStrings.xml")
    except KeyError:
        return []
    root = ET.fromstring(xml)
    namespace = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    strings = []
    for item in root.findall("x:si", namespace):
        strings.append("".join(text.text or "" for text in item.findall(".//x:t", namespace)))
    return strings


def _first_sheet_name(archive: zipfile.ZipFile) -> str:
    for name in archive.namelist():
        if name.startswith("xl/worksheets/sheet") and name.endswith(".xml"):
            return name
    raise KeyError("sheet")


def _cell_column_index(cell_ref: str) -> int:
    letters = "".join(char for char in cell_ref if char.isalpha()).upper()
    index = 0
    for char in letters:
        index = index * 26 + (ord(char) - ord("A") + 1)
    return max(index - 1, 0)


def _cell_text(cell: ET.Element, shared_strings: list[str], namespace: dict[str, str]) -> str:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        return "".join(text.text or "" for text in cell.findall(".//x:t", namespace))
    value_node = cell.find("x:v", namespace)
    value = value_node.text if value_node is not None else ""
    if cell_type == "s" and value:
        try:
            return shared_strings[int(value)]
        except (ValueError, IndexError):
            return ""
    return value or ""


def _build_simple_xlsx(rows: list[list[str]]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _xlsx_content_types())
        archive.writestr("_rels/.rels", _xlsx_root_rels())
        archive.writestr("xl/workbook.xml", _xlsx_workbook())
        archive.writestr("xl/_rels/workbook.xml.rels", _xlsx_workbook_rels())
        archive.writestr("xl/worksheets/sheet1.xml", _xlsx_sheet(rows))
    return output.getvalue()


def _xlsx_content_types() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>"""


def _xlsx_root_rels() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>"""


def _xlsx_workbook() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<sheets><sheet name="Products" sheetId="1" r:id="rId1"/></sheets>
</workbook>"""


def _xlsx_workbook_rels() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>"""


def _xlsx_sheet(rows: list[list[str]]) -> str:
    xml_rows = []
    for row_index, row in enumerate(rows, start=1):
        cells = []
        for column_index, value in enumerate(row, start=1):
            cell_ref = f"{_xlsx_column_name(column_index)}{row_index}"
            escaped = _escape_xml(str(value or ""))
            cells.append(f'<c r="{cell_ref}" t="inlineStr"><is><t>{escaped}</t></is></c>')
        xml_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<sheetData>{"".join(xml_rows)}</sheetData>
</worksheet>'''


def _xlsx_column_name(index: int) -> str:
    name = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(ord("A") + remainder) + name
    return name


def _escape_xml(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
