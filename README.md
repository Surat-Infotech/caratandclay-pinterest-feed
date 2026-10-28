# Carat & Clay — Pinterest catalog feed (private)

Builds the product feed for the Pinterest catalog "Carat & Clay – Fine Jewelry (US)" from caratandclay.com.

- `scrape_products.py` reads every product in https://caratandclay.com/product-sitemap.xml (name, description, prices, sale prices, metals, photos) from the data each product page already shows. It retries server errors and stops below a minimum product count.
- `build_feed.py` writes `pinterest-feed.csv`: one item per product per metal, keyword-led titles, regular + sale price, Google category, product type and custom labels for product groups. Images are served as JPEG through wsrv.nl.
- `.github/workflows/feed.yml` runs both every day at 05:00 UTC and pushes only the CSV to the public repo
  `Surat-Infotech/caratandclay-pinterest-feed-public`. Pinterest reads it daily from:
  **https://raw.githubusercontent.com/Surat-Infotech/caratandclay-pinterest-feed-public/main/pinterest-feed.csv**
  If fewer than 900 products can be read (site down), the run stops and yesterday's feed stays online.

Setup: secret `FEED_PUSH_TOKEN` = fine-grained token, resource owner Surat-Infotech, only the public repo, Contents: Read and write.

Run locally: `python scrape_products.py products.json && python build_feed.py products.json pinterest-feed.csv`
