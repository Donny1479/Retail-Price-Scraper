from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"

REQUIRED_COLUMNS = {
    "week_start",
    "scrape_date",
    "retailer_id",
    "product_id",
    "matched_product_name",
    "regular_retail",
    "special_retail",
    "on_sale",
    "currency",
    "product_url",
    "url_status",
    "seller",
    "availability",
    "confidence",
    "notes",
}

PRICE_COLUMNS = ("regular_retail", "special_retail")
AVAILABILITY_VALUES = {"", "in_stock", "out_of_stock", "not_found", "not_listed", "unavailable", "unclear"}
URL_STATUS_VALUES = {"", "matched", "search_result", "not_found", "not_listed", "blocked", "unclear"}


def read_ids(path: Path, column: str) -> set[str]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return {row[column].strip() for row in csv.DictReader(handle) if row.get(column, "").strip()}


def valid_price(value: str) -> bool:
    cleaned = value.replace("$", "").replace(",", "").strip()
    if cleaned == "":
        return True
    try:
        return float(cleaned) >= 0
    except ValueError:
        return False


def validate_file(path: Path, product_ids: set[str], retailer_ids: set[str]) -> list[str]:
    errors: list[str] = []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            return [f"{path}: file has no header row"]

        columns = {name.strip() for name in reader.fieldnames}
        missing = REQUIRED_COLUMNS - columns
        if missing:
            errors.append(f"{path}: missing required columns: {', '.join(sorted(missing))}")

        for row_number, row in enumerate(reader, start=2):
            product_id = row.get("product_id", "").strip()
            retailer_id = row.get("retailer_id", "").strip()
            if product_id and product_id not in product_ids:
                errors.append(f"{path}:{row_number}: unknown product_id '{product_id}'")
            if retailer_id and retailer_id not in retailer_ids:
                errors.append(f"{path}:{row_number}: unknown retailer_id '{retailer_id}'")
            for column in PRICE_COLUMNS:
                if not valid_price(row.get(column, "")):
                    errors.append(f"{path}:{row_number}: {column} is not a valid non-negative price")
            currency = row.get("currency", "").strip()
            if currency and currency != "CAD":
                errors.append(f"{path}:{row_number}: currency should be CAD")
            availability = row.get("availability", "").strip()
            if availability not in AVAILABILITY_VALUES:
                errors.append(f"{path}:{row_number}: availability should be one of {', '.join(sorted(AVAILABILITY_VALUES - {''}))}")
            url_status = row.get("url_status", "").strip()
            if url_status not in URL_STATUS_VALUES:
                errors.append(f"{path}:{row_number}: url_status should be one of {', '.join(sorted(URL_STATUS_VALUES - {''}))}")
    return errors


def validate(paths: Iterable[Path]) -> int:
    product_ids = read_ids(DATA_DIR / "products.csv", "product_id")
    retailer_ids = read_ids(DATA_DIR / "retailers.csv", "retailer_id")

    errors: list[str] = []
    for path in paths:
        errors.extend(validate_file(path, product_ids, retailer_ids))

    if errors:
        for error in errors:
            print(error)
        return 1
    print("Scrape file validation passed.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate weekly retail scrape CSV files.")
    parser.add_argument("files", nargs="+", type=Path)
    args = parser.parse_args()
    return validate(args.files)


if __name__ == "__main__":
    raise SystemExit(main())
