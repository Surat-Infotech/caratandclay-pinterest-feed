"""Read every Carat & Clay product from caratandclay.com into products.json.

Source: the product sitemap (https://caratandclay.com/product-sitemap.xml) and the product data
that each product page already embeds for the browser (Next.js flight data). /api/ is not used
(robots.txt disallows it).

Usage: python scrape_products.py [out.json]
"""
import concurrent.futures as cf
import json
import re
import sys
import time
import urllib.request

UA = "Mozilla/5.0 (CaratAndClay catalog builder)"
SITEMAP = "https://caratandclay.com/product-sitemap.xml"


def get(url, tries=3):
    for n in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode("utf-8", "replace")
        except Exception:
            if n == tries - 1:
                raise
            time.sleep(2 * (n + 1))


def flight(html):
    chunks = re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)\s*</script>', html, re.S)
    return "".join(json.loads('"' + c + '"') for c in chunks)


def product_object(text, slug):
    """Return the first JSON object that has "slug":"<slug>" and product fields."""
    dec = json.JSONDecoder()
    for m in re.finditer(r'"slug":"%s"' % re.escape(slug), text):
        start = text.rfind('{"id":', 0, m.start())
        if start < 0:
            continue
        try:
            obj, _ = dec.raw_decode(text, start)
        except ValueError:
            continue
        if obj.get("slug") == slug and ("imageSets" in obj or "metalPrices" in obj or "variants" in obj):
            return obj
    return None


def ld_product(html):
    for s in re.findall(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', html, re.S):
        try:
            d = json.loads(s)
        except ValueError:
            continue
        if isinstance(d, dict) and d.get("@type") == "Product":
            return d
    return {}


def scrape(url):
    slug = url.rstrip("/").split("/")[-1]
    html = get(url)
    obj = product_object(flight(html), slug)
    return {"url": url, "slug": slug, "ld": ld_product(html), "data": obj}


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "products.json"
    urls = re.findall(r"<loc>([^<]+)</loc>", get(SITEMAP))
    print(len(urls), "product urls", flush=True)
    results, failed = [], []
    with cf.ThreadPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(scrape, u): u for u in urls}
        for i, f in enumerate(cf.as_completed(futs), 1):
            try:
                results.append(f.result())
            except Exception as e:
                failed.append((futs[f], str(e)))
            if i % 100 == 0:
                print(i, "done", flush=True)
    # The site sometimes answers 500 under load: retry those one by one, slowly.
    still = []
    for u, _ in failed:
        try:
            results.append(scrape(u))
            time.sleep(0.7)
        except Exception as e:
            still.append((u, str(e)))
    results = [r for r in results if r["data"]]  # drops collection pages listed in the sitemap
    json.dump({"products": results, "failed": still}, open(out, "w"))
    print(f"saved {len(results)} products, {len(still)} failed -> {out}")
    min_ok = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    if len(results) < min_ok:
        sys.exit(f"only {len(results)} products (< {min_ok}); not publishing")


if __name__ == "__main__":
    main()
