from __future__ import annotations

import argparse
import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"

REQUIRED_COLUMNS = {
    "retailer_id",
    "product_id",
    "product_url",
    "url_status",
    "matched_product_name",
    "last_checked",
    "seller",
    "notes",
}

URL_STATUS_VALUES = {"", "matched", "search_result", "not_found", "not_listed", "blocked", "unclear"}


def read_ids(path: Path, column: str) -> set[str]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return {row[column].strip() for row in csv.DictReader(handle) if row.get(column, "").strip()}


def validate(path: Path) -> int:
    product_ids = read_ids(DATA_DIR / "products.csv", "product_id")
    retailer_ids = read_ids(DATA_DIR / "retailers.csv", "retailer_id")
    errors: list[str] = []

    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            errors.append(f"{path}: file has no header row")
        else:
            columns = {name.strip() for name in reader.fieldnames}
            missing = REQUIRED_COLUMNS - columns
            if missing:
                errors.append(f"{path}: missing required columns: {', '.join(sorted(missing))}")

        seen: set[tuple[str, str]] = set()
        for row_number, row in enumerate(reader, start=2):
            product_id = row.get("product_id", "").strip()
            retailer_id = row.get("retailer_id", "").strip()
            pair = (retailer_id, product_id)
            if product_id and product_id not in product_ids:
                errors.append(f"{path}:{row_number}: unknown product_id '{product_id}'")
            if retailer_id and retailer_id not in retailer_ids:
                errors.append(f"{path}:{row_number}: unknown retailer_id '{retailer_id}'")
            if pair in seen:
                errors.append(f"{path}:{row_number}: duplicate retailer_id/product_id pair {pair}")
            seen.add(pair)
            url_status = row.get("url_status", "").strip()
            if url_status not in URL_STATUS_VALUES:
                errors.append(f"{path}:{row_number}: invalid url_status '{url_status}'")
            product_url = row.get("product_url", "").strip()
            if url_status == "matched" and not product_url:
                errors.append(f"{path}:{row_number}: matched rows should include product_url")

    if errors:
        for error in errors:
            print(error)
        return 1
    print("URL cache validation passed.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate retailer-product URL cache.")
    parser.add_argument("file", type=Path, nargs="?", default=DATA_DIR / "product_urls.csv")
    args = parser.parse_args()
    return validate(args.file)


if __name__ == "__main__":
    raise SystemExit(main())
