"""Build the Pinterest catalog feed (CSV) from products.json.

One feed item per product per metal (item_group_id = product slug), with keyword-led titles,
plain-text descriptions, the metal's own photos, regular + sale price, Google category,
product type and custom labels for product groups.

Images: the site stores WebP. Pinterest documents JPEG/PNG best, so image links go through
wsrv.nl (free open-source image proxy) which returns a JPEG of the same file.

Usage: python build_feed.py [products.json] [pinterest-feed.csv]
"""
import csv
import html
import json
import re
import sys
from urllib.parse import quote

UTM = "utm_source=pinterest&utm_medium=catalog&utm_campaign=pinterest_catalog"
BRAND = "Carat & Clay"
TRUST_DIAMOND = ("Every lab grown diamond is IGI or GIA certified. Finished by hand in New York. "
                 "Free insured shipping and 30-day returns.")
TRUST_PLAIN = "Finished by hand in New York. Free insured shipping and 30-day returns."

# Metal keys used by ring settings -> (display name, color, material)
SETTING_METALS = {
    "yellow-gold": ("14K Yellow Gold", "Yellow Gold", "14K Gold"),
    "white-gold": ("14K White Gold", "White Gold", "14K Gold"),
    "rose-gold": ("14K Rose Gold", "Rose Gold", "14K Gold"),
    "platinum": ("Platinum", "White", "Platinum"),
}

# Site category -> (Google product category, product type root, keyword noun used in titles)
CATS = {
    "earrings": ("Apparel & Accessories > Jewelry > Earrings", "Jewelry > Earrings", "Earrings"),
    "pendants": ("Apparel & Accessories > Jewelry > Necklaces", "Jewelry > Pendant Necklaces", "Pendant Necklace"),
    "necklaces": ("Apparel & Accessories > Jewelry > Necklaces", "Jewelry > Necklaces", "Necklace"),
    "chains": ("Apparel & Accessories > Jewelry > Necklaces", "Jewelry > Chains", "Chain Necklace"),
    "bracelets": ("Apparel & Accessories > Jewelry > Bracelets", "Jewelry > Bracelets", "Bracelet"),
    "wedding-rings": ("Apparel & Accessories > Jewelry > Rings", "Jewelry > Rings", "Ring"),
    "settings": ("Apparel & Accessories > Jewelry > Rings", "Engagement Rings > Ring Settings", "Engagement Ring Setting"),
}

# Sub-category -> title keyword (from search research: wedding band, tennis bracelet, diamond studs, …)
SUB_KEYWORD = {
    "mens": "Men's Wedding Band", "plain-band": "Wedding Band", "pave": "Diamond Wedding Band",
    "eternity": "Diamond Eternity Band", "anniversary": "Anniversary Ring", "channel-set": "Diamond Wedding Band",
    "vintage": "Vintage Wedding Band", "fashion": "Ring", "wedding-rings-solitaire": "Solitaire Ring",
    "bracelets-tennis": "Diamond Tennis Bracelet", "necklaces-tennis": "Diamond Tennis Necklace",
    "studs": "Diamond Stud Earrings", "hoops": "Hoop Earrings", "huggies": "Huggie Earrings", "drop": "Drop Earrings",
    "initial": "Initial Necklace", "heart": "Heart Necklace", "cross": "Cross Necklace",
    "solitaire": "Diamond Pendant Necklace", "halo": "Halo Diamond Pendant",
}

STYLE_KEYWORD = {
    "solitaire": "Solitaire", "hidden-halo": "Hidden Halo", "halo": "Halo", "pave": "Pavé",
    "three-stone": "Three Stone", "side-stone": "Side Stone", "vintage": "Vintage", "cathedral": "Cathedral",
    "bezel": "Bezel", "cluster": "Cluster", "unique": "Unique",
}


def clean(s):
    s = html.unescape(s or "")
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def jpg(url):
    return "https://wsrv.nl/?url=" + quote(url.replace("https://", ""), safe="/") + "&output=jpg&q=90"


def money(x):
    return f"{float(x):.2f} USD"


def has_diamonds(text):
    t = text.lower()
    if "no diamond" in t or "plain metal" in t:
        return False
    return any(w in t for w in ("diamond", "pavé", "pave", "lab grown", "lab-grown", "tennis", "eternity", "halo"))


def price_band(p):
    for limit, label in ((500, "under-500"), (1000, "500-1000"), (2000, "1000-2000"), (3500, "2000-3500")):
        if p < limit:
            return label
    return "3500-plus"


def add_noun(name, noun):
    """Append the search noun if the product name doesn't already say it."""
    key = noun.lower().replace("diamond ", "").split()[-1].rstrip("s")
    return name if key in name.lower() else f"{name} {noun}"


def title_for(name, metal, keyword, diamonds):
    t = add_noun(name, keyword)
    if diamonds and "diamond" not in t.lower():
        t += " with Lab Grown Diamonds"
    elif diamonds and "lab" not in t.lower():
        t = t.replace("Diamond", "Lab Grown Diamond", 1)
    return f"{t} in {metal}"[:150]


def row(**kw):
    return kw


def jewelry_items(p):
    d = p["data"]
    parent = d.get("parentCategorySlug") or "jewelry"
    sub = d.get("categorySlug") or ""
    gcat, ptype, noun = CATS.get(parent, CATS["necklaces"])
    keyword = SUB_KEYWORD.get(sub) or SUB_KEYWORD.get(f"{parent}-{sub}") or noun
    if parent == "earrings" and "earring" not in keyword.lower():
        keyword += " Earrings"
    desc_src = " ".join(filter(None, [d.get("description"), d.get("shortDescription"), d.get("metaDescription")]))
    diamonds = has_diamonds(desc_src + " " + d["name"])
    variants = [v for v in d.get("variants", []) if v.get("isActive", True)]

    def variant_for(purity):
        vs = [v for v in variants if any(o["value"] == purity for o in v["options"])] or variants
        return min(vs, key=lambda v: float(v.get("salePrice") or v["price"])) if vs else None

    has18 = any(o["value"] == "18K Gold" for v in variants for o in v["options"])
    out = []
    for s in d.get("imageSets", []):
        metal = next((o["value"] for o in s.get("options", []) if o.get("optionTypeName") == "Metal"), None)
        if not metal:
            continue
        v = variant_for("Platinum" if metal == "Platinum" else "14K Gold")
        if not v:
            continue
        imgs = [m["url"] for m in sorted(s["media"], key=lambda m: m.get("displayOrder", 0)) if m.get("mediaType") == "image"]
        if not imgs:
            continue
        price, sale = float(v["price"]), float(v.get("salePrice") or 0)
        color = metal.replace("14K ", "") if metal != "Platinum" else "White"
        material = "Platinum" if metal == "Platinum" else "14K Gold"
        desc = clean(d.get("description") or d.get("shortDescription"))
        extra = f" Also available in 18K gold." if has18 and metal != "Platinum" else ""
        desc = f"{desc} Shown in {metal}.{extra} {TRUST_DIAMOND if diamonds else TRUST_PLAIN}"
        style_word = SUB_KEYWORD.get(sub, sub.replace("-", " ").title())
        out.append(row(
            id=f"{v['sku']}-{metal.upper().replace(' ', '-')}"[:127],
            item_group_id=p["slug"][:127],
            title=title_for(d["name"], metal, keyword, diamonds),
            description=desc[:10000],
            link=f"{p['url']}?{UTM}",
            image_link=jpg(imgs[0]),
            additional_image_link=",".join(jpg(u) for u in imgs[1:10]),
            price=money(price),
            sale_price=money(sale) if 0 < sale < price else "",
            availability="in stock",
            condition="new",
            brand=BRAND,
            google_product_category=gcat,
            product_type=f"{ptype} > {style_word}" if sub else ptype,
            color=color, material=material,
            gender="male" if sub == "mens" else "female", age_group="adult",
            variant_names="Metal", variant_values=metal,
            custom_label_0=parent, custom_label_1=color.lower().replace(" ", "-"),
            custom_label_2=price_band(sale if 0 < sale < price else price),
            custom_label_3=sub or parent, custom_label_4="lab-grown-diamond" if diamonds else "plain-gold",
        ))
    return out


def setting_items(p):
    d = p["data"]
    style = d.get("style") or ""
    shapes = ", ".join(s.title() for s in (d.get("compatibleShapes") or []))
    gcat, ptype, _ = CATS["settings"]
    name = d["name"]
    if style == "solitaire" and "solitaire" not in name.lower():
        name = "Solitaire " + name
    base_desc = clean(d.get("description") or p["ld"].get("description"))
    out = []
    for key, (metal, color, material) in SETTING_METALS.items():
        mp = (d.get("metalPrices") or {}).get(key)
        if not mp or not mp.get("images"):
            continue
        price = float(mp.get("originalPrice") or mp["price"])
        sale = float(mp["price"])
        has18 = f"18k-{key}" in (d.get("metalPrices") or {})
        desc = (f"{base_desc} Ring setting only, shown in {metal}: choose your own certified lab grown center diamond "
                f"(IGI or GIA) and we build the ring.{' Fits ' + shapes + ' diamonds.' if shapes else ''}"
                f"{' Also available in 18K gold.' if has18 else ''} Finished by hand in New York. "
                f"Free insured shipping and 30-day returns.")
        imgs = mp["images"]
        out.append(row(
            id=f"{(d.get('sku') or p['slug'])}-{key.upper()}"[:127],
            item_group_id=p["slug"][:127],
            title=f"{name} in {metal}"[:150],
            description=desc,
            link=f"{p['url']}?{UTM}",
            image_link=jpg(imgs[0]),
            additional_image_link=",".join(jpg(u) for u in imgs[1:10]),
            price=money(price),
            sale_price=money(sale) if 0 < sale < price else "",
            availability="in stock",
            condition="new",
            brand=BRAND,
            google_product_category=gcat,
            product_type=f"{ptype} > {STYLE_KEYWORD.get(style, style.title())}",
            color=color, material=material,
            gender="female", age_group="adult",
            variant_names="Metal", variant_values=metal,
            custom_label_0="engagement-ring-settings", custom_label_1=color.lower().replace(" ", "-"),
            custom_label_2=price_band(sale), custom_label_3=style or "setting",
            custom_label_4="lab-grown-diamond",
        ))
    return out


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else "products.json"
    out = sys.argv[2] if len(sys.argv) > 2 else "pinterest-feed.csv"
    products = json.load(open(src))["products"]
    items = []
    for p in products:
        if not p.get("data"):
            continue
        items += setting_items(p) if "metalPrices" in p["data"] else jewelry_items(p)
    seen, uniq = set(), []
    for it in items:  # ids must be unique
        if it["id"] not in seen:
            seen.add(it["id"])
            uniq.append(it)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(uniq[0].keys()), quoting=csv.QUOTE_ALL)
        w.writeheader()
        w.writerows(uniq)
    print(f"{len(uniq)} items from {len(products)} products -> {out}")


if __name__ == "__main__":
    main()
