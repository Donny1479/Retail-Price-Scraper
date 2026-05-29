from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd
import streamlit as st


ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
SCRAPE_DIR = DATA_DIR / "scrapes"
PRODUCTS_PATH = DATA_DIR / "products.csv"
RETAILERS_PATH = DATA_DIR / "retailers.csv"
PRODUCT_URLS_PATH = DATA_DIR / "product_urls.csv"

REQUIRED_SCRAPE_COLUMNS = {
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

PRICE_ALIASES = {
    "regular_price": "regular_retail",
    "special_price": "special_retail",
    "week": "week_start",
}


st.set_page_config(
    page_title="Tim Hortons CPG Price Tracker",
    layout="wide",
    initial_sidebar_state="expanded",
)


st.markdown(
    """
    <style>
    :root {
        --th-red: #b5121b;
        --ink: #1f2933;
        --muted: #667085;
        --line: #e5e7eb;
        --panel: #ffffff;
        --wash: #f6f7f9;
        --accent: #087f8c;
    }
    .main .block-container {
        padding-top: 1.2rem;
        padding-bottom: 2.5rem;
        max-width: 1500px;
    }
    h1, h2, h3 {
        color: var(--ink);
        letter-spacing: 0;
    }
    h1 {
        font-size: 2rem;
        margin-bottom: .2rem;
    }
    [data-testid="stSidebar"] {
        background: #f9fafb;
        border-right: 1px solid var(--line);
    }
    div[data-testid="stMetric"] {
        background: var(--panel);
        border: 1px solid var(--line);
        border-radius: 8px;
        padding: .85rem 1rem;
        box-shadow: 0 1px 2px rgba(16, 24, 40, .05);
    }
    div[data-testid="stMetricLabel"] p {
        color: var(--muted);
        font-size: .78rem;
    }
    div[data-testid="stMetricValue"] {
        color: var(--ink);
        font-size: 1.55rem;
    }
    .section-band {
        border-top: 1px solid var(--line);
        padding-top: .65rem;
        margin-top: .4rem;
    }
    .small-note {
        color: var(--muted);
        font-size: .88rem;
    }
    .sale-chip {
        color: #9f1239;
        font-weight: 700;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def normalize_columns(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    frame.columns = [str(c).strip() for c in frame.columns]
    frame = frame.rename(columns={k: v for k, v in PRICE_ALIASES.items() if k in frame.columns})
    return frame


@st.cache_data(show_spinner=False)
def load_products() -> pd.DataFrame:
    products = pd.read_csv(PRODUCTS_PATH, dtype=str).fillna("")
    products["product_label"] = products["item_description"] + " (" + products["size_qty"] + " " + products["size_uom"] + ")"
    products["segment_label"] = products["segment"].str.strip()
    products["brand_group"] = products["brand_group"].replace("", "Unassigned")
    return products


@st.cache_data(show_spinner=False)
def load_retailers() -> pd.DataFrame:
    retailers = pd.read_csv(RETAILERS_PATH, dtype=str).fillna("")
    retailers["retailer_label"] = retailers["retailer"] + " - " + retailers["market"]
    return retailers


@st.cache_data(show_spinner=False)
def load_product_urls() -> pd.DataFrame:
    if not PRODUCT_URLS_PATH.exists():
        return pd.DataFrame(
            columns=[
                "retailer_id",
                "product_id",
                "product_url",
                "url_status",
                "matched_product_name",
                "last_checked",
                "seller",
                "notes",
            ]
        )
    return pd.read_csv(PRODUCT_URLS_PATH, dtype=str).fillna("")


def parse_price(series: pd.Series) -> pd.Series:
    cleaned = (
        series.fillna("")
        .astype(str)
        .str.replace("$", "", regex=False)
        .str.replace(",", "", regex=False)
        .str.strip()
    )
    cleaned = cleaned.replace({"": pd.NA, "nan": pd.NA, "None": pd.NA})
    return pd.to_numeric(cleaned, errors="coerce")


def parse_bool(series: pd.Series) -> pd.Series:
    truthy = {"true", "yes", "y", "1", "sale", "on sale"}
    return series.fillna("").astype(str).str.strip().str.lower().isin(truthy)


def normalize_scrape_frame(frame: pd.DataFrame, source_name: str) -> pd.DataFrame:
    frame = normalize_columns(frame)
    for column in REQUIRED_SCRAPE_COLUMNS:
        if column not in frame.columns:
            frame[column] = ""

    frame = frame.copy()
    frame["source_file"] = source_name
    frame["week_start"] = pd.to_datetime(frame["week_start"], errors="coerce").dt.date.astype("string")
    frame["scrape_date"] = pd.to_datetime(frame["scrape_date"], errors="coerce").dt.date.astype("string")
    frame["regular_retail"] = parse_price(frame["regular_retail"])
    frame["special_retail"] = parse_price(frame["special_retail"])
    frame["on_sale"] = parse_bool(frame["on_sale"]) | frame["special_retail"].notna()
    frame["effective_retail"] = frame["special_retail"].where(frame["special_retail"].notna(), frame["regular_retail"])
    frame["sale_depth"] = (frame["regular_retail"] - frame["special_retail"]) / frame["regular_retail"]
    frame.loc[~frame["on_sale"] | frame["regular_retail"].isna(), "sale_depth"] = pd.NA
    frame["availability"] = frame["availability"].replace("", "unclear")
    frame["url_status"] = frame["url_status"].replace("", "unclear")
    return frame


@st.cache_data(show_spinner=False)
def load_scrape_files() -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    SCRAPE_DIR.mkdir(parents=True, exist_ok=True)
    for path in sorted(SCRAPE_DIR.glob("*.csv")):
        if path.name.startswith("_"):
            continue
        try:
            raw = pd.read_csv(path, dtype=str)
        except pd.errors.EmptyDataError:
            continue
        frames.append(normalize_scrape_frame(raw, path.name))
    if not frames:
        return pd.DataFrame(columns=sorted(REQUIRED_SCRAPE_COLUMNS | {"source_file", "effective_retail", "sale_depth"}))
    return pd.concat(frames, ignore_index=True)


def format_money(value: object) -> str:
    if pd.isna(value):
        return ""
    return f"${float(value):,.2f}"


def format_percent(value: object) -> str:
    if pd.isna(value):
        return ""
    return f"{float(value) * 100:.1f}%"


def display_status(row: pd.Series) -> str:
    price = format_money(row.get("effective_retail"))
    if price:
        return f"{price} sale" if bool(row.get("on_sale")) else price

    availability = str(row.get("availability", "")).strip().lower()
    url_status = str(row.get("url_status", "")).strip().lower()
    if availability in {"not_found", "not listed", "not_listed"} or url_status in {"not_found", "not_listed"}:
        return "not found"
    if availability == "out_of_stock":
        return "out of stock"
    if url_status in {"blocked", "unclear"}:
        return url_status
    return availability or url_status or "unpriced"


def size_to_base(row: pd.Series) -> tuple[float | None, str]:
    raw_qty = str(row.get("size_qty", "")).strip()
    uom = str(row.get("size_uom", "")).strip().upper()
    qty = pd.to_numeric(raw_qty, errors="coerce")
    if pd.isna(qty):
        return None, ""
    qty = float(qty)
    if uom in {"GR", "G"}:
        return qty, "100 g"
    if uom == "KG":
        return qty * 1000, "100 g"
    if uom == "ML":
        return qty, "100 mL"
    if uom == "L":
        return qty * 1000, "100 mL"
    if uom == "EA":
        return qty, "each"
    return None, ""


def add_price_per_unit(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    if frame.empty:
        frame["base_qty"] = pd.Series(dtype="float64")
        frame["unit_basis"] = pd.Series(dtype="string")
        frame["price_per_unit"] = pd.Series(dtype="float64")
        return frame
    bases = frame.apply(size_to_base, axis=1, result_type="expand")
    frame["base_qty"] = pd.to_numeric(bases[0], errors="coerce")
    frame["unit_basis"] = bases[1]
    frame["price_per_unit"] = pd.NA

    mass_or_volume = frame["unit_basis"].isin(["100 g", "100 mL"]) & frame["base_qty"].gt(0)
    each = frame["unit_basis"].eq("each") & frame["base_qty"].gt(0)
    frame.loc[mass_or_volume, "price_per_unit"] = frame.loc[mass_or_volume, "effective_retail"] / frame.loc[mass_or_volume, "base_qty"] * 100
    frame.loc[each, "price_per_unit"] = frame.loc[each, "effective_retail"] / frame.loc[each, "base_qty"]
    return frame


def apply_filters(
    frame: pd.DataFrame,
    weeks: Iterable[str],
    segments: Iterable[str],
    retailers: Iterable[str],
    brand_groups: Iterable[str],
    products: Iterable[str],
    sale_status: str,
) -> pd.DataFrame:
    filtered = frame.copy()
    if weeks:
        filtered = filtered[filtered["week_start"].isin(weeks)]
    if segments:
        filtered = filtered[filtered["segment"].isin(segments)]
    if retailers:
        filtered = filtered[filtered["retailer"].isin(retailers)]
    if brand_groups:
        filtered = filtered[filtered["brand_group"].isin(brand_groups)]
    if products:
        filtered = filtered[filtered["item_description"].isin(products)]
    if sale_status == "On sale":
        filtered = filtered[filtered["on_sale"]]
    elif sale_status == "Regular only":
        filtered = filtered[~filtered["on_sale"] & filtered["effective_retail"].notna()]
    elif sale_status == "Unavailable":
        filtered = filtered[filtered["effective_retail"].isna()]
    return filtered


def display_frame(frame: pd.DataFrame, columns: list[str]) -> None:
    visible = frame.loc[:, [c for c in columns if c in frame.columns]].copy()
    for column in ["regular_retail", "special_retail", "effective_retail", "price_per_unit"]:
        if column in visible:
            visible[column] = visible[column].map(format_money)
    if "sale_depth" in visible:
        visible["sale_depth"] = visible["sale_depth"].map(format_percent)
    st.dataframe(visible, use_container_width=True, hide_index=True)


products = load_products()
retailers = load_retailers()
product_urls = load_product_urls()
scrapes = load_scrape_files()
for column in REQUIRED_SCRAPE_COLUMNS:
    if column not in scrapes.columns:
        scrapes[column] = ""

data = scrapes.merge(products, on="product_id", how="left").merge(retailers, on="retailer_id", how="left")
data["item_description"] = data["item_description"].fillna(data["matched_product_name"])
data["segment"] = data["segment"].fillna("Unmapped")
data["retailer"] = data["retailer"].fillna(data["retailer_id"])
data["brand_group"] = data["brand_group"].fillna("Unmapped")
data["availability"] = data["availability"].fillna("unclear").replace("", "unclear")
data["url_status"] = data["url_status"].fillna("unclear").replace("", "unclear")
if "notes_x" in data.columns:
    data["notes"] = data["notes_x"].fillna("")
elif "notes" not in data.columns:
    data["notes"] = ""
data = add_price_per_unit(data)

st.title("Tim Hortons CPG Price Tracker")
st.caption("Weekly Canadian retail reads for Tim Hortons CPG products and tracked competitive items.")

with st.sidebar:
    st.header("Filters")
    st.caption("Weekly data loads automatically from CSV files committed to `data/scrapes/`.")
    week_options = sorted([w for w in data["week_start"].dropna().unique() if w], reverse=True)
    selected_weeks = st.multiselect("Week", week_options, default=week_options[:1])
    segment_options = sorted(products["segment"].dropna().unique())
    selected_segments = st.multiselect("Segment", segment_options)
    retailer_options = sorted(retailers["retailer"].dropna().unique())
    selected_retailers = st.multiselect("Retailer", retailer_options)
    brand_group_options = sorted(products["brand_group"].dropna().unique())
    selected_brand_groups = st.multiselect("Brand group", brand_group_options)
    product_source = products
    if selected_segments:
        product_source = product_source[product_source["segment"].isin(selected_segments)]
    product_options = sorted(product_source["item_description"].dropna().unique())
    selected_products = st.multiselect("Product", product_options)
    sale_status = st.radio("Price status", ["All", "On sale", "Regular only", "Unavailable"], horizontal=False)

filtered = apply_filters(
    data,
    selected_weeks,
    selected_segments,
    selected_retailers,
    selected_brand_groups,
    selected_products,
    sale_status,
)

priced = filtered[filtered["effective_retail"].notna()].copy()
total_products = products["product_id"].nunique()
seen_products = priced["product_id"].nunique()

metric_cols = st.columns(5)
metric_cols[0].metric("Price observations", f"{len(priced):,}")
metric_cols[1].metric("Products seen", f"{seen_products:,} / {total_products:,}")
metric_cols[2].metric("Retailers seen", f"{priced['retailer_id'].nunique():,}")
metric_cols[3].metric("Average retail", format_money(priced["effective_retail"].mean()) if not priced.empty else "")
unpriced_count = int(filtered["effective_retail"].isna().sum()) if "effective_retail" in filtered else 0
metric_cols[4].metric("Unpriced / gaps", f"{unpriced_count:,}")

if scrapes.empty:
    st.info("No weekly scrape files are present yet. The product and retailer trackers are ready for the first CSV drop.")

tab_price, tab_retailer, tab_trends, tab_coverage, tab_urls, tab_master = st.tabs(
    ["Price Board", "Retailer View", "Trends", "Coverage", "URL Cache", "Product Master"]
)

with tab_price:
    st.subheader("Price Board")
    if filtered.empty:
        st.warning("No rows match the current filters.")
    else:
        board = filtered.copy()
        board["display_price"] = board.apply(display_status, axis=1)
        pivot = board.pivot_table(
            index=["segment", "item_description"],
            columns="retailer",
            values="display_price",
            aggfunc="last",
            fill_value="",
        ).reset_index()
        st.dataframe(pivot, use_container_width=True, hide_index=True)

        st.markdown('<div class="section-band"></div>', unsafe_allow_html=True)
        st.subheader("Observation Detail")
        display_frame(
            filtered.sort_values(["segment", "item_description", "retailer", "week_start"]),
            [
                "week_start",
                "scrape_date",
                "segment",
                "item_description",
                "brand_group",
                "retailer",
                "regular_retail",
                "special_retail",
                "effective_retail",
                "price_per_unit",
                "unit_basis",
                "on_sale",
                "sale_depth",
                "url_status",
                "availability",
                "seller",
                "product_url",
                "notes",
            ],
        )
        st.download_button(
            "Download filtered CSV",
            filtered.to_csv(index=False).encode("utf-8"),
            file_name="filtered_price_tracker.csv",
            mime="text/csv",
        )

with tab_retailer:
    st.subheader("Retailer View")
    if priced.empty:
        st.warning("No priced rows are available for the current filters.")
    else:
        retailer_summary = (
            priced.groupby("retailer", dropna=False)
            .agg(
                observations=("effective_retail", "count"),
                products=("product_id", "nunique"),
                avg_regular=("regular_retail", "mean"),
                avg_effective=("effective_retail", "mean"),
                median_effective=("effective_retail", "median"),
                sale_reads=("on_sale", "sum"),
            )
            .reset_index()
            .sort_values(["products", "observations"], ascending=False)
        )
        retailer_summary["sale_rate"] = retailer_summary["sale_reads"] / retailer_summary["observations"]
        for col in ["avg_regular", "avg_effective", "median_effective"]:
            retailer_summary[col] = retailer_summary[col].map(format_money)
        retailer_summary["sale_rate"] = retailer_summary["sale_rate"].map(format_percent)
        st.dataframe(retailer_summary, use_container_width=True, hide_index=True)

        top_products = (
            priced.groupby(["segment", "item_description"], dropna=False)["effective_retail"]
            .agg(["min", "mean", "max", "count"])
            .reset_index()
            .rename(columns={"min": "low", "mean": "average", "max": "high", "count": "retailer_reads"})
            .sort_values(["segment", "item_description"])
        )
        for col in ["low", "average", "high"]:
            top_products[col] = top_products[col].map(format_money)
        st.markdown('<div class="section-band"></div>', unsafe_allow_html=True)
        st.subheader("Product Price Spread")
        st.dataframe(top_products, use_container_width=True, hide_index=True)

with tab_trends:
    st.subheader("Trends")
    if priced.empty or priced["week_start"].nunique() < 2:
        st.info("Trend charts appear after at least two weekly files have priced observations.")
    else:
        trend_product_options = sorted(priced["item_description"].dropna().unique())
        trend_product = st.selectbox("Trend product", trend_product_options)
        trend = priced[priced["item_description"].eq(trend_product)]
        trend = (
            trend.groupby(["week_start", "retailer"], dropna=False)["effective_retail"]
            .mean()
            .reset_index()
            .pivot(index="week_start", columns="retailer", values="effective_retail")
            .sort_index()
        )
        st.line_chart(trend)

        segment_trend = (
            priced.groupby(["week_start", "segment"], dropna=False)["effective_retail"]
            .mean()
            .reset_index()
            .pivot(index="week_start", columns="segment", values="effective_retail")
            .sort_index()
        )
        st.markdown('<div class="section-band"></div>', unsafe_allow_html=True)
        st.subheader("Average Retail by Segment")
        st.line_chart(segment_trend)

with tab_coverage:
    st.subheader("Coverage")
    base_products = products.copy()
    if selected_segments:
        base_products = base_products[base_products["segment"].isin(selected_segments)]
    if selected_products:
        base_products = base_products[base_products["item_description"].isin(selected_products)]
    selected_retailer_ids = retailers
    if selected_retailers:
        selected_retailer_ids = selected_retailer_ids[selected_retailer_ids["retailer"].isin(selected_retailers)]

    coverage = filtered.copy()
    coverage["has_price"] = coverage["effective_retail"].notna()
    if coverage.empty:
        st.info("Coverage will populate when scrape rows are present.")
    else:
        coverage["coverage_status"] = coverage.apply(display_status, axis=1)
        coverage_matrix = coverage.pivot_table(
            index=["segment", "item_description"],
            columns="retailer",
            values="coverage_status",
            aggfunc="last",
            fill_value="",
        ).reset_index()
        st.dataframe(coverage_matrix, use_container_width=True, hide_index=True)

        missing = coverage[coverage["effective_retail"].isna()]
        missing_view = missing[["week_start", "segment", "item_description", "retailer", "url_status", "availability", "product_url", "notes"]]
        if not missing_view.empty:
            st.markdown('<div class="section-band"></div>', unsafe_allow_html=True)
            st.subheader("Unpriced, Not Found, or Not Listed")
            st.dataframe(missing_view, use_container_width=True, hide_index=True)

    st.markdown('<p class="small-note">Tracked scope: '
                f'{base_products["product_id"].nunique()} products across '
                f'{selected_retailer_ids["retailer_id"].nunique()} retailers.</p>',
                unsafe_allow_html=True)

with tab_urls:
    st.subheader("URL Cache")
    if product_urls.empty:
        st.info("The reusable product URL cache is ready. The first scrape should populate `data/product_urls.csv`.")
    else:
        url_view = product_urls.merge(products, on="product_id", how="left").merge(retailers, on="retailer_id", how="left")
        if "notes_x" in url_view.columns:
            url_view["notes"] = url_view["notes_x"].fillna("")
        elif "notes" not in url_view.columns:
            url_view["notes"] = ""
        if selected_segments:
            url_view = url_view[url_view["segment"].isin(selected_segments)]
        if selected_retailers:
            url_view = url_view[url_view["retailer"].isin(selected_retailers)]
        if selected_products:
            url_view = url_view[url_view["item_description"].isin(selected_products)]
        st.dataframe(
            url_view[
                [
                    "retailer",
                    "segment",
                    "item_description",
                    "matched_product_name",
                    "url_status",
                    "product_url",
                    "last_checked",
                    "seller",
                    "notes",
                ]
            ],
            use_container_width=True,
            hide_index=True,
        )

with tab_master:
    st.subheader("Product Master")
    master_view = products.copy()
    if selected_segments:
        master_view = master_view[master_view["segment"].isin(selected_segments)]
    if selected_brand_groups:
        master_view = master_view[master_view["brand_group"].isin(selected_brand_groups)]
    if selected_products:
        master_view = master_view[master_view["item_description"].isin(selected_products)]
    st.dataframe(
        master_view[
            [
                "product_id",
                "segment",
                "item_description",
                "brand_group",
                "brand",
                "upc",
                "size_qty",
                "size_uom",
                "notes",
            ]
        ],
        use_container_width=True,
        hide_index=True,
    )

    st.markdown('<div class="section-band"></div>', unsafe_allow_html=True)
    st.subheader("Retailer Master")
    st.dataframe(retailers, use_container_width=True, hide_index=True)
