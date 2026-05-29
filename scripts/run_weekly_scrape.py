from __future__ import annotations

import csv
import datetime as dt
import json
import math
import re
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, urljoin

import pandas as pd
import requests
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
SCRAPE_DIR = DATA_DIR / "scrapes"
SKILL_URL_CACHE = Path.home() / ".codex" / "skills" / "retail-cpg-price-scrape" / "references" / "product-url-cache.md"

SCRAPE_DATE = dt.date.today()
WEEK_START = SCRAPE_DATE - dt.timedelta(days=SCRAPE_DATE.weekday())

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-CA,en;q=0.9",
}

LOBLAW_DOMAINS = {
    "rcss": "https://www.realcanadiansuperstore.ca",
    "loblaws": "https://www.loblaws.ca",
    "no_frills": "https://www.nofrills.ca",
}

BLOCKED_RETAILERS = {
    "walmart": "https://www.walmart.ca/search?q={query}",
    "sobeys": "https://www.sobeys.com/en/search-results/?q={query}",
    "freshco": "https://www.freshco.com/search/?q={query}",
    "iga_qc": "https://www.iga.net/en/search?k={query}",
    "metro_on": "https://www.metro.ca/en/online-grocery/search?filter={query}",
    "metro_qc": "https://www.metro.ca/en/online-grocery/search?filter={query}",
    "food_basics": "https://www.foodbasics.ca/search?filter={query}",
    "canadian_tire": "https://www.canadiantire.ca/en/search-results.html?q={query}",
}

PRIVATE_LABEL_BRANDS = {
    "walmart": ["Great Value", "Equate"],
    "rcss": ["President's Choice", "PC", "No Name"],
    "loblaws": ["President's Choice", "PC", "No Name"],
    "no_frills": ["President's Choice", "PC", "No Name"],
}

QUERY_OVERRIDES = {
    "sku_001": "Tim Hortons Chicken Noodle Soup 540 mL",
    "sku_002": "Tim Hortons Italian Wedding Soup 540 mL",
    "sku_003": "Tim Hortons Tomato Condensed Soup 284 mL",
    "sku_004": "Tim Hortons Chili 425 g",
    "sku_012": "Tim Hortons Original Blend K-Cup 12 count",
    "sku_013": "Tim Hortons Original Blend K-Cup 30 count",
    "sku_014": "Tim Hortons Tea K-Cup 12 count",
    "sku_015": "Tim Hortons Original Blend K-Cup 48 count",
    "sku_016": "Tim Hortons Barista Medium K-Cup 10 count",
    "sku_021": "Tim Hortons Nespresso compatible Classic Lungo 10 count",
    "sku_024": "Tim Hortons Instant Coffee Medium 100 g",
    "sku_025": "Tim Hortons Instant Coffee Medium 300 g",
    "sku_030": "Tim Hortons Original Blend Ground Coffee 652 g",
    "sku_031": "Tim Hortons Original Whole Bean Coffee 907 g",
    "sku_032": "Tim Hortons Original Blend Ground Coffee 300 g",
    "sku_033": "Tim Hortons Original Fine Grind Coffee 875 g",
    "sku_034": "Tim Hortons Decaf Coffee 640 g",
    "sku_039": "Tim Hortons Hot Chocolate 500 g",
    "sku_040": "Tim Hortons Hot Chocolate 1.5 kg",
    "sku_041": "Tim Hortons French Vanilla Cappuccino 8 count",
    "sku_042": "Tim Hortons French Vanilla Cappuccino 454 g",
    "sku_043": "Tim Hortons French Vanilla Cappuccino 1 kg",
    "sku_044": "Tim Hortons Peppermint Tea 20 count",
    "sku_045": "Tim Hortons Iced Coffee Syrup Cappuccino 470 mL",
    "sku_023": "private label coffee pods 12 30 count",
    "sku_029": "private label instant coffee 100 g",
}

REQUIRED_TERMS = {
    "sku_001": [["chicken"], ["noodle"], ["540"]],
    "sku_002": [["italian"], ["wedding"], ["540"]],
    "sku_003": [["tomato"], ["284"]],
    "sku_004": [["chili", "chilli"], ["425"]],
    "sku_005": [["chunky"], ["chicken"], ["noodle"], ["515"]],
    "sku_006": [["herbed"], ["chicken"], ["515"]],
    "sku_007": [["tomato"], ["284"]],
    "sku_008": [["stagg"], ["chili", "chilli"], ["425"]],
    "sku_009": [["cream"], ["chicken"], ["284"]],
    "sku_010": [["pea"], ["796"]],
    "sku_011": [["tomato"], ["284"]],
    "sku_012": [["original"], ["12"], ["k cup", "kcup", "pod"]],
    "sku_013": [["original"], ["30"], ["k cup", "kcup", "pod"]],
    "sku_014": [["tea"], ["12"], ["k cup", "kcup", "pod"]],
    "sku_015": [["original"], ["48"], ["k cup", "kcup", "pod"]],
    "sku_016": [["10"], ["k cup", "kcup", "pod"], ["brew", "ice", "barista"]],
    "sku_017": [["medium"], ["dark"], ["30"], ["k cup", "kcup", "pod"]],
    "sku_020": [["medium"], ["dark"], ["48"], ["k cup", "kcup", "pod"]],
    "sku_021": [["classic"], ["lungo"], ["10"]],
    "sku_022": [["pike"], ["place"], ["nespresso", "capsule"], ["10"]],
    "sku_023": [["pod", "k cup", "kcup"], ["12", "30"]],
    "sku_024": [["instant"], ["100"]],
    "sku_025": [["instant"], ["300"]],
    "sku_026": [["gold"], ["espresso"], ["100"]],
    "sku_027": [["sweet"], ["creamy"], ["vanilla"], ["18"]],
    "sku_028": [["rich"], ["instant"]],
    "sku_029": [["instant"], ["100"]],
    "sku_030": [["original"], ["652"]],
    "sku_031": [["whole"], ["bean"], ["907", "2lb", "2 lb"]],
    "sku_032": [["original"], ["300"]],
    "sku_033": [["fine"], ["grind"], ["875"]],
    "sku_034": [["decaf"], ["640"]],
    "sku_035": [["original"], ["roast"], ["864"]],
    "sku_036": [["medium"], ["dark"], ["875"], ["ground", "roast"]],
    "sku_037": [["french"], ["roast"], ["340"]],
    "sku_038": [["three"], ["sisters"], ["454"]],
    "sku_039": [["hot"], ["chocolate"], ["500"]],
    "sku_040": [["hot"], ["chocolate"], ["1.5", "1 5", "1500"]],
    "sku_041": [["french"], ["vanilla"], ["8"]],
    "sku_042": [["french"], ["vanilla"], ["454"]],
    "sku_043": [["french"], ["vanilla"], ["1kg", "1 kg", "1000"]],
    "sku_044": [["peppermint"], ["20"]],
    "sku_045": [["iced"], ["coffee"], ["syrup"], ["470"]],
    "sku_046": [["earl"], ["grey", "gray"], ["vanilla"]],
    "sku_047": [["peppermint"], ["20"]],
    "sku_048": [["medium"], ["roast"], ["unsweetened"], ["1.42", "1420"]],
    "sku_049": [["black"], ["unsweetened"], ["1.42", "1420"]],
}

UNWANTED_TERMS = {
    "sku_031": ["& maple", "bundle"],
}


@dataclass
class Candidate:
    title: str
    url: str
    price: float | None
    was_price: float | None
    seller: str
    availability: str
    source_status: str
    raw_text: str


def clean_money(value: object) -> float | None:
    if value is None:
        return None
    text = str(value).replace("$", "").replace(",", "").strip()
    if not text:
        return None
    match = re.search(r"\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def normalized_tokens(text: str) -> set[str]:
    replacements = {
        "tdl": "tim hortons",
        "th": "tim hortons",
        "k-cup": "kcup",
        "k cup": "kcup",
        "mccafe": "mccafe",
        "mc café": "mccafe",
        "mcafé": "mccafe",
    }
    text = text.lower()
    for old, new in replacements.items():
        text = text.replace(old, new)
    return {token for token in re.findall(r"[a-z0-9]+", text) if len(token) > 1}


def brand_matches(product: pd.Series, retailer_id: str, raw: str) -> bool:
    raw = raw.lower()
    brand_group = product["brand_group"]
    brand = str(product["brand"]).lower().replace("'", "").replace("é", "e")
    raw_plain = raw.replace("'", "").replace("é", "e")
    if brand_group == "Tim Hortons":
        return "tim hortons" in raw_plain
    if brand_group == "Private Label":
        return any(label.lower().replace("'", "") in raw_plain for label in PRIVATE_LABEL_BRANDS.get(retailer_id, []))
    if brand and brand != "unspecified":
        return brand in raw_plain
    return True


def required_terms_match(product: pd.Series, raw: str) -> bool:
    product_id = product["product_id"]
    raw_plain = raw.lower().replace("-", " ").replace(",", " ")
    raw_compact = re.sub(r"[^a-z0-9.]+", "", raw_plain)
    if product["brand"].lower() == "unspecified":
        return False
    for alternatives in REQUIRED_TERMS.get(product_id, []):
        found = False
        for term in alternatives:
            term_plain = term.lower()
            term_compact = re.sub(r"[^a-z0-9.]+", "", term_plain)
            if term_plain in raw_plain or term_compact in raw_compact:
                found = True
                break
        if not found:
            return False
    return True


def multipack_mismatch(product: pd.Series, raw: str) -> bool:
    raw = raw.lower()
    if product["product_id"] in {"sku_023"}:
        return False
    patterns = [
        r"\bpack of\s+(?!1\b)\d+",
        r"\b[2-9]\d?\s*pack\b",
        r"\b[2-9]\d?\s*boxes\b",
        r"\b[2-9]\d?\s*box\b",
        r"\b[2-9]\d?\s*-\s*pack\b",
        r"\b[2-9]\d?\s*x\s*\d+",
        r"\bper case\b",
        r"\bcase\b",
    ]
    if any(re.search(pattern, raw) for pattern in patterns):
        return True
    if product["size_uom"].lower() not in {"ea"} and re.search(r"\b[2-9]\d?\s*count\b", raw):
        return True
    return False


def rejected_by_detail_rules(product: pd.Series, retailer_id: str, raw: str) -> bool:
    expected = product_expected_text(product, retailer_id).lower()
    if not brand_matches(product, retailer_id, raw):
        return True
    if not required_terms_match(product, raw):
        return True
    if multipack_mismatch(product, raw):
        return True
    if "decaf" in raw.lower() and "decaf" not in expected:
        return True
    if any(term in raw.lower() for term in UNWANTED_TERMS.get(product["product_id"], [])):
        return True
    return False


def normalize_availability(text: str) -> str:
    value = (text or "").strip().lower()
    if not value:
        return "unclear"
    if "in stock" in value or "left in stock" in value or "ships within" in value:
        return "in_stock"
    if "currently unavailable" in value or "out of stock" in value:
        return "out_of_stock"
    if value in {"in_stock", "out_of_stock", "not_found", "not_listed", "unavailable", "unclear"}:
        return value
    return "unclear"


def base_query(product: pd.Series, retailer_id: str) -> str:
    product_id = product["product_id"]
    if product_id in {"sku_023", "sku_029"} and retailer_id in PRIVATE_LABEL_BRANDS:
        if product_id == "sku_023":
            if retailer_id == "walmart":
                return "Great Value coffee pods 12 count"
            return "President's Choice coffee pods 12 count"
        if retailer_id == "walmart":
            return "Great Value instant coffee 100 g"
        return "No Name instant coffee 100 g"
    if product_id in QUERY_OVERRIDES:
        return QUERY_OVERRIDES[product_id]
    desc = product["item_description"]
    brand = product["brand"]
    size = f"{product['size_qty']} {product['size_uom']}".replace("GR", "g").replace("EA", "count")
    if product["brand_group"] == "Tim Hortons":
        desc = desc.replace("TDL", "").replace("TH", "").replace("TIM HORTONS", "")
        return f"Tim Hortons {desc} {size}".strip()
    return f"{brand} {desc} {size}".strip()


def product_expected_text(product: pd.Series, retailer_id: str) -> str:
    if product["brand_group"] == "Private Label":
        brands = " ".join(PRIVATE_LABEL_BRANDS.get(retailer_id, ["private label"]))
        return f"{brands} {product['item_description']} {product['size_qty']} {product['size_uom']}"
    return f"{product['brand']} {product['item_description']} {product['size_qty']} {product['size_uom']}"


def score_candidate(product: pd.Series, retailer_id: str, candidate: Candidate) -> float:
    expected = product_expected_text(product, retailer_id)
    expected_tokens = normalized_tokens(expected)
    candidate_tokens = normalized_tokens(candidate.raw_text)
    if not candidate_tokens:
        return 0
    raw = candidate.raw_text.lower()
    if not brand_matches(product, retailer_id, raw):
        return 0
    if not required_terms_match(product, raw):
        return 0

    score = len(expected_tokens & candidate_tokens) * 1.4
    score += len(normalized_tokens(base_query(product, retailer_id)) & candidate_tokens) * 0.6

    brand_group = product["brand_group"]
    brand = str(product["brand"]).lower()
    if brand_group == "Tim Hortons" and "tim hortons" in raw:
        score += 6
    elif brand_group == "Private Label":
        if any(label.lower() in raw for label in PRIVATE_LABEL_BRANDS.get(retailer_id, [])):
            score += 6
    elif brand and brand != "unspecified" and brand in raw:
        score += 5

    qty = str(product["size_qty"]).strip()
    uom = str(product["size_uom"]).strip().lower()
    if qty and qty.lower() != "nan":
        qty_parts = [part for part in re.split(r"[/ ]+", qty) if part]
        if any(re.search(rf"\b{re.escape(part)}\b", raw) for part in qty_parts):
            score += 5
        elif uom in {"ml", "l", "g", "gr", "kg", "ea"}:
            numbers = [float(n) for n in re.findall(r"\b\d+(?:\.\d+)?\b", raw)]
            expected_numbers = []
            for part in qty_parts:
                try:
                    expected_numbers.append(float(part))
                except ValueError:
                    pass
            if expected_numbers and numbers:
                if not any(math.isclose(n, e, rel_tol=0, abs_tol=0.01) for n in numbers for e in expected_numbers):
                    score -= 4

    if multipack_mismatch(product, raw):
        return 0
    if "decaf" in raw and "decaf" not in product_expected_text(product, retailer_id).lower():
        return 0
    if any(term in raw for term in UNWANTED_TERMS.get(product["product_id"], [])):
        return 0

    if product["segment"] == "Soup & Chili" and not any(t in raw for t in ["soup", "chili", "chilli"]):
        score -= 5
    if product["segment"] == "Tea" and "tea" not in raw:
        score -= 4
    if product["segment"] == "Instant" and "instant" not in raw and product["brand_group"] != "Private Label":
        score -= 3
    if product["segment"] == "RTD" and not any(t in raw for t in ["cold", "iced", "brew", "unsweetened"]):
        score -= 2

    return score


def choose_best(product: pd.Series, retailer_id: str, candidates: list[Candidate]) -> tuple[Candidate | None, float]:
    if not candidates:
        return None, 0
    scored = [(score_candidate(product, retailer_id, c), c) for c in candidates]
    scored.sort(key=lambda item: item[0], reverse=True)
    best_score, best = scored[0]
    threshold = 11 if product["brand_group"] != "Private Label" else 8
    if best_score < threshold:
        return None, best_score
    return best, best_score


def fetch(session: requests.Session, url: str) -> requests.Response:
    response = session.get(url, headers=HEADERS, timeout=35)
    response.raise_for_status()
    return response


def parse_walmart(session: requests.Session, product: pd.Series) -> tuple[list[Candidate], str]:
    query = base_query(product, "walmart")
    search_url = f"https://www.walmart.ca/search?q={quote(query)}"
    response = fetch(session, search_url)
    soup = BeautifulSoup(response.text, "html.parser")
    script = soup.find("script", id="__NEXT_DATA__")
    candidates: list[Candidate] = []
    if not script or not script.string:
        return candidates, search_url
    data = json.loads(script.string)
    stacks = data.get("props", {}).get("pageProps", {}).get("initialData", {}).get("searchResult", {}).get("itemStacks", [])
    for stack in stacks:
        for item in stack.get("items", []):
            seller = item.get("sellerName") or ""
            if seller and seller.lower() != "walmart":
                continue
            price_info = item.get("priceInfo") or {}
            title = item.get("name") or ""
            relative = item.get("canonicalUrl") or ""
            url = urljoin("https://www.walmart.ca", relative)
            raw_text = " ".join(
                str(part)
                for part in [
                    title,
                    item.get("brand"),
                    item.get("type"),
                    price_info.get("unitPrice"),
                    item.get("salesUnit"),
                ]
                if part
            )
            candidates.append(
                Candidate(
                    title=title,
                    url=url,
                    price=clean_money(item.get("price") or price_info.get("linePrice")),
                    was_price=clean_money(price_info.get("wasPrice")),
                    seller=seller or "Walmart",
                    availability=(item.get("availabilityStatusDisplayValue") or "").lower().replace(" ", "_") or "unclear",
                    source_status="matched",
                    raw_text=raw_text,
                )
            )
    return candidates, search_url


def parse_loblaw(session: requests.Session, product: pd.Series, retailer_id: str) -> tuple[list[Candidate], str]:
    domain = LOBLAW_DOMAINS[retailer_id]
    query = base_query(product, retailer_id)
    search_url = f"{domain}/search?search-bar={quote(query)}"
    response = fetch(session, search_url)
    soup = BeautifulSoup(response.text, "html.parser")
    script = soup.find("script", id="__NEXT_DATA__")
    candidates: list[Candidate] = []
    if not script or not script.string:
        return candidates, search_url
    data = json.loads(script.string)
    sections = data.get("props", {}).get("pageProps", {}).get("initialSearchData", {}).get("layout", {}).get("sections", {})
    components = sections.get("mainContentCollection", {}).get("components", [])
    for component in components:
        tiles = component.get("data", {}).get("productTiles", [])
        for tile in tiles:
            pricing = tile.get("pricing") or {}
            brand = tile.get("brand") or ""
            title = tile.get("title") or ""
            package = tile.get("packageSizing") or ""
            relative = tile.get("link") or ""
            candidates.append(
                Candidate(
                    title=" ".join([brand, title]).strip(),
                    url=urljoin(domain, relative),
                    price=clean_money(pricing.get("price") or pricing.get("displayPrice")),
                    was_price=clean_money(pricing.get("wasPrice")),
                    seller=domain.replace("https://www.", ""),
                    availability="in_stock",
                    source_status="matched",
                    raw_text=" ".join([brand, title, package, str(tile.get("description") or "")]),
                )
            )
    return candidates, search_url


def parse_amazon_search_item(item) -> Candidate | None:
    title_region = item.select_one('[data-cy="title-recipe"]')
    title = title_region.get_text(" ", strip=True) if title_region else item.get_text(" ", strip=True)[:180]
    price = item.select_one(".a-price .a-offscreen")
    link = item.select_one("a.a-link-normal.s-no-outline") or item.select_one("h2 a")
    if not link:
        return None
    return Candidate(
        title=title,
        url=urljoin("https://www.amazon.ca", link.get("href", "")),
        price=clean_money(price.get_text(strip=True) if price else ""),
        was_price=None,
        seller="Amazon.ca search result",
        availability="unclear",
        source_status="search_result",
        raw_text=item.get_text(" ", strip=True)[:1500],
    )


def parse_amazon_detail(session: requests.Session, candidate: Candidate) -> Candidate:
    try:
        response = fetch(session, candidate.url)
    except Exception:
        return candidate
    soup = BeautifulSoup(response.text, "html.parser")
    if soup.find(id="captchacharacters"):
        return candidate
    title = soup.select_one("#productTitle")
    availability = soup.select_one("#availability")
    core_price = soup.select_one("#corePrice_feature_div .a-price .a-offscreen") or soup.select_one(".a-price .a-offscreen")
    text = soup.get_text(" ", strip=True)
    sold_by = ""
    match = re.search(r"Ships from:\s*([^:]+?)\s*Sold by:\s*([^:]+?)(?:\s{2,}|$)", text)
    if match:
        sold_by = f"Ships from {match.group(1).strip()}; Sold by {match.group(2).strip()}"
    elif "Sold by:" in text:
        sold_by = text[text.find("Sold by:") : text.find("Sold by:") + 160]
    return Candidate(
        title=title.get_text(" ", strip=True) if title else candidate.title,
        url=candidate.url.split("/ref=")[0],
        price=clean_money(core_price.get_text(strip=True) if core_price else candidate.price),
        was_price=candidate.was_price,
        seller=sold_by or candidate.seller,
        availability=(availability.get_text(" ", strip=True).lower().replace(" ", "_") if availability else candidate.availability),
        source_status="matched",
        raw_text=" ".join([candidate.raw_text, title.get_text(" ", strip=True) if title else ""]),
    )


def parse_amazon(session: requests.Session, product: pd.Series) -> tuple[list[Candidate], str]:
    query = base_query(product, "amazon_ca")
    search_url = f"https://www.amazon.ca/s?k={quote(query)}"
    response = fetch(session, search_url)
    soup = BeautifulSoup(response.text, "html.parser")
    if soup.find(id="captchacharacters") or response.status_code in {429, 503}:
        return [], search_url
    candidates = []
    for item in soup.select('[data-component-type="s-search-result"]')[:12]:
        candidate = parse_amazon_search_item(item)
        if candidate:
            candidates.append(candidate)
    return candidates, search_url


def row_from_candidate(retailer_id: str, product: pd.Series, candidate: Candidate, score: float) -> dict[str, object]:
    regular = candidate.price
    special = None
    on_sale = False
    if candidate.was_price and candidate.price and candidate.was_price > candidate.price:
        regular = candidate.was_price
        special = candidate.price
        on_sale = True
    notes = []
    if score < 14:
        notes.append("Product matched by name/size with medium confidence; verify if business-critical.")
    return {
        "week_start": WEEK_START.isoformat(),
        "scrape_date": SCRAPE_DATE.isoformat(),
        "retailer_id": retailer_id,
        "product_id": product["product_id"],
        "matched_product_name": candidate.title,
        "regular_retail": regular if regular is not None else "",
        "special_retail": special if special is not None else "",
        "on_sale": str(on_sale).lower(),
        "currency": "CAD",
        "product_url": candidate.url,
        "url_status": candidate.source_status,
        "seller": candidate.seller,
        "availability": normalize_availability(candidate.availability),
        "confidence": "high" if score >= 16 else "medium",
        "notes": " ".join(notes),
    }


def not_found_row(retailer_id: str, product: pd.Series, search_url: str, status: str, note: str, confidence: str = "low") -> dict[str, object]:
    return {
        "week_start": WEEK_START.isoformat(),
        "scrape_date": SCRAPE_DATE.isoformat(),
        "retailer_id": retailer_id,
        "product_id": product["product_id"],
        "matched_product_name": "",
        "regular_retail": "",
        "special_retail": "",
        "on_sale": "false",
        "currency": "CAD",
        "product_url": search_url,
        "url_status": status,
        "seller": "",
        "availability": "unclear" if status == "blocked" else status,
        "confidence": confidence,
        "notes": note,
    }


def url_cache_row(row: dict[str, object]) -> dict[str, object]:
    return {
        "retailer_id": row["retailer_id"],
        "product_id": row["product_id"],
        "product_url": row["product_url"],
        "url_status": row["url_status"],
        "matched_product_name": row["matched_product_name"],
        "last_checked": row["scrape_date"],
        "seller": row["seller"],
        "notes": row["notes"],
    }


def scrape_product(session: requests.Session, retailer_id: str, product: pd.Series) -> dict[str, object]:
    if retailer_id == "walmart":
        search_url = BLOCKED_RETAILERS[retailer_id].format(query=quote(base_query(product, retailer_id)))
        return not_found_row(
            retailer_id,
            product,
            search_url,
            "blocked",
            "Walmart began returning bot-block pages during automated scraping; needs browser/manual retry with Walmart session access.",
        )
    elif retailer_id in LOBLAW_DOMAINS:
        candidates, search_url = parse_loblaw(session, product, retailer_id)
    elif retailer_id == "amazon_ca":
        try:
            candidates, search_url = parse_amazon(session, product)
        except Exception as exc:
            search_url = f"https://www.amazon.ca/s?k={quote(base_query(product, retailer_id))}"
            return not_found_row(retailer_id, product, search_url, "blocked", f"Amazon search failed or blocked: {exc}")
        best, score = choose_best(product, retailer_id, candidates)
        if best:
            best = parse_amazon_detail(session, best)
            if rejected_by_detail_rules(product, retailer_id, best.title):
                return not_found_row(
                    retailer_id,
                    product,
                    search_url,
                    "not_found",
                    "Amazon result was rejected after detail-page title/package validation.",
                )
            return row_from_candidate(retailer_id, product, best, score)
        return not_found_row(retailer_id, product, search_url, "not_found", "No matching Amazon.ca search result passed product name/size checks.")
    elif retailer_id in BLOCKED_RETAILERS:
        search_url = BLOCKED_RETAILERS[retailer_id].format(query=quote(base_query(product, retailer_id)))
        return not_found_row(
            retailer_id,
            product,
            search_url,
            "blocked",
            "Retailer search page blocked automated access or requires interactive browser verification.",
        )
    else:
        search_url = ""
        return not_found_row(retailer_id, product, search_url, "unclear", "No scraper implemented for this retailer.")

    best, score = choose_best(product, retailer_id, candidates)
    if best:
        return row_from_candidate(retailer_id, product, best, score)
    note = "No retailer-sold exact or high-confidence product match found by name/size search."
    return not_found_row(retailer_id, product, search_url, "not_found", note)


def write_skill_url_cache(url_rows: list[dict[str, object]], retailers: pd.DataFrame, products: pd.DataFrame) -> None:
    if not SKILL_URL_CACHE.parent.exists():
        return
    retailer_lookup = retailers.set_index("retailer_id")["retailer"].to_dict()
    product_lookup = products.set_index("product_id")["item_description"].to_dict()
    lines = [
        "# Product URL Cache",
        "",
        f"Last updated from scrape: {SCRAPE_DATE.isoformat()}",
        "",
        "Use `data/product_urls.csv` as the editable source of truth. Durable findings from the latest scrape are mirrored below.",
        "",
        "| retailer | product_id | product | url_status | product_url | matched_product_name | seller | notes |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for row in url_rows:
        values = [
            retailer_lookup.get(row["retailer_id"], row["retailer_id"]),
            row["product_id"],
            product_lookup.get(row["product_id"], ""),
            row["url_status"],
            row["product_url"],
            row["matched_product_name"],
            row["seller"],
            row["notes"],
        ]
        escaped = [str(v).replace("|", "\\|").replace("\n", " ") for v in values]
        lines.append("| " + " | ".join(escaped) + " |")
    SKILL_URL_CACHE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    products = pd.read_csv(DATA_DIR / "products.csv", dtype=str).fillna("")
    retailers = pd.read_csv(DATA_DIR / "retailers.csv", dtype=str).fillna("")
    SCRAPE_DIR.mkdir(parents=True, exist_ok=True)
    session = requests.Session()

    rows: list[dict[str, object]] = []
    url_rows: list[dict[str, object]] = []
    total = len(products) * len(retailers)
    count = 0
    for _, retailer in retailers.iterrows():
        retailer_id = retailer["retailer_id"]
        print(f"Scraping {retailer['retailer']} ({retailer_id})")
        for _, product in products.iterrows():
            count += 1
            try:
                row = scrape_product(session, retailer_id, product)
            except Exception as exc:
                row = not_found_row(
                    retailer_id,
                    product,
                    "",
                    "blocked",
                    f"Scrape exception for retailer/product: {type(exc).__name__}: {exc}",
                )
            rows.append(row)
            url_rows.append(url_cache_row(row))
            if count % 25 == 0:
                print(f"  {count}/{total} rows")
            time.sleep(0.25 if retailer_id in {"walmart", "amazon_ca"} or retailer_id in LOBLAW_DOMAINS else 0)

    scrape_path = SCRAPE_DIR / f"{WEEK_START.isoformat()}_price_scrape.csv"
    fieldnames = [
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
    ]
    with scrape_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    url_path = DATA_DIR / "product_urls.csv"
    url_fieldnames = [
        "retailer_id",
        "product_id",
        "product_url",
        "url_status",
        "matched_product_name",
        "last_checked",
        "seller",
        "notes",
    ]
    with url_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=url_fieldnames)
        writer.writeheader()
        writer.writerows(url_rows)

    write_skill_url_cache(url_rows, retailers, products)

    print(f"Wrote {scrape_path}")
    print(f"Wrote {url_path}")
    print(pd.DataFrame(rows)["url_status"].value_counts(dropna=False).to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
