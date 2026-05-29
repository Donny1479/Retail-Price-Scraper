# Retail Price Scraper

Streamlit dashboard for weekly Canadian retail price reads across Tim Hortons CPG products and tracked competitors.

## Run locally

```powershell
pip install -r requirements.txt
streamlit run app.py
```

## Weekly data flow

Add one CSV per scrape week to `data/scrapes/` and push it to GitHub. The Streamlit app reads those committed files automatically; users do not upload data through the site. Use `data/scrape_template.csv` as the schema.

Required columns:

```text
week_start,scrape_date,retailer_id,product_id,matched_product_name,regular_retail,special_retail,on_sale,currency,product_url,url_status,seller,availability,confidence,notes
```

Use `week_start` as the Monday date for the reporting week. Use blank `special_retail` when the item is not on sale. Use blank prices with `url_status`, `availability`, and `notes` when an item is not found, not listed, blocked, or unavailable.

The first scrape should also populate `data/product_urls.csv`. This cache keeps the best known retailer product page for each `retailer_id` and `product_id`, plus a `url_status` such as `matched`, `not_found`, `not_listed`, `blocked`, or `unclear`.

Validate new files before pushing:

```powershell
python scripts/validate_url_cache.py data/product_urls.csv
python scripts/validate_scrape_file.py data/scrapes/<file>.csv
```

## Master data

- `data/products.csv` stores the tracked Tim Hortons, competitor, and private label products.
- `data/retailers.csv` stores retailer scope, postal-code context, and seller validation rules.
- `data/product_urls.csv` stores reusable retailer-product URLs discovered during scrape runs.
