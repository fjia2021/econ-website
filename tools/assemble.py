#!/usr/bin/env python3
"""Assembles finished pages from src/pages/<slug>/ (output of wix_import.py).

    python tools/assemble.py [slug ...]
"""
import html
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = "https://www.econworldtrading.com"
GTM = "GTM-PHB4L7GZ"
FAVICON = ("https://static.wixstatic.com/media/16f9b6_c691cd20ae1e4cd5ace170d6023eae04~mv2.png"
           "/v1/fill/w_{s},h_{s},lg_1,usm_0.66_1.00_0.01/16f9b6_c691cd20ae1e4cd5ace170d6023eae04~mv2.png")


DATA = ROOT / "data"
GALLERIES = json.loads((DATA / "galleries.json").read_text(encoding="utf-8"))
ITEMS = json.loads((DATA / "gallery_items.json").read_text(encoding="utf-8"))
RIBBONS = json.loads((DATA / "gallery_ribbons.json").read_text(encoding="utf-8"))
MEDIA = "https://static.wixstatic.com/media/"


def gallery_html(slug, comp, page_size, root, cols=3):
    """Product grid replacing a Wix Stores gallery: same items, order, ribbons and paging."""
    e = html.escape
    page_gals = GALLERIES.get(slug, {})
    order = page_gals.get(comp) or (next(iter(page_gals.values())) if len(page_gals) == 1 else [])
    ribbons = RIBBONS.get(slug, {})
    lis = []
    for i, ps in enumerate(order):
        it = ITEMS.get(ps, {})
        name, uri = it.get("name", ps), it.get("image", "")
        img = (f'<img src="{MEDIA}{uri}/v1/fill/w_400,h_400,al_c,q_85,usm_0.66_1.00_0.01,enc_auto/{uri}" '
               f'srcset="{MEDIA}{uri}/v1/fill/w_400,h_400,al_c,q_85,usm_0.66_1.00_0.01,enc_auto/{uri} 1x, '
               f'{MEDIA}{uri}/v1/fill/w_800,h_800,al_c,q_85,usm_0.66_1.00_0.01,enc_auto/{uri} 2x" '
               f'alt="{e(name)}" loading="lazy" width="306" height="306">') if uri else ""
        rib = ribbons.get(ps, "")
        rib_html = f'<span class="pgal-ribbon">{e(rib)}</span>' if rib else ""
        hidden = " is-hidden" if page_size and i >= page_size else ""
        lis.append(f'<li class="pgal-item{hidden}"><a href="{root}product-page/{ps}/">'
                   f'<div class="pgal-img">{img}{rib_html}</div><p class="pgal-name">{e(name)}</p></a></li>')
    more = (f'<div class="pgal-more-wrap"><button class="pgal-load" type="button" data-step="{page_size}">Load More</button></div>'
            if page_size and len(order) > page_size else "")
    return (f'<section class="pgal" aria-label="Product Gallery"><ul class="pgal-list" style="grid-template-columns:repeat({cols},1fr)">'
            f'{"".join(lis)}</ul>{more}</section>')


def fill_galleries(body, slug, root):
    return re.sub(r"<!--STOREGAL:([^:]+):(\d+):(\d+)-->",
                  lambda m: gallery_html(slug, m.group(1), int(m.group(2)), root, int(m.group(3))), body)


PRODUCT_TEMPLATE = "product-page_atosa-reach-in-refrigerator-two-section"
PRODUCTS = {p["slug"]: p for p in json.loads((DATA / "products.json").read_text(encoding="utf-8"))}
DESCRIPTIONS = json.loads((DATA / "descriptions.json").read_text(encoding="utf-8"))
NOTE = ('<p>Currently we are not accepting online orders, for further information or to purchase please call us at '
        '<a href="tel:5106512799">(510) 651-2799</a> or email <a href="mailto:info@econworldtrading.com">'
        'info@econworldtrading.com</a></p>')


def product_html(ps, root):
    e = html.escape
    p, it = PRODUCTS.get(ps, {}), ITEMS.get(ps, {})
    name = it.get("name") or p.get("name") or ps
    images = list(p.get("images") or ([it["image"]] if it.get("image") else []))

    def src(uri, w, h):
        return f"{MEDIA}{uri}/v1/fit/w_{w},h_{h},q_90,usm_0.66_1.00_0.01,enc_auto/{uri}"
    main = (f'<img id="pp-main" src="{src(images[0], 500, 526)}" srcset="{src(images[0], 500, 526)} 1x, '
            f'{src(images[0], 1000, 1052)} 2x" alt="{e(name)}" width="500" height="526">') if images else ""
    thumbs = ""
    if len(images) > 1:
        thumbs = '<div class="pp-thumbs">' + "".join(
            f'<button type="button" data-full="{src(u, 1000, 1052)}"><img src="{src(u, 120, 120)}" alt=""></button>'
            for u in images) + "</div>"
    desc = DESCRIPTIONS.get(ps)
    if desc is None and p.get("desc"):
        desc = f"<p>{e(p['desc'])}</p>"
    return f"""<div class="ppage">
<nav class="pp-crumbs" aria-label="Breadcrumbs"><a href="{root}">Home</a> / {e(name)}</nav>
<a class="pp-back" href="javascript:history.back()" aria-label="Back"><svg viewBox="0 0 24 24" width="24" height="24"><path d="M15 5l-7 7 7 7" fill="none" stroke="currentColor" stroke-width="1.5"/></svg></a>
<div class="pp-grid">
<div class="pp-media"><div class="pp-imgbox">{main}</div>{thumbs}</div>
<div class="pp-head"><h1 class="pp-title">{e(name)}</h1>
<div class="pp-qty-label">Quantity <span>*</span></div>
<div class="pp-qty"><button type="button" aria-label="Decrease">&minus;</button><input type="number" value="1" min="1" aria-label="Quantity"><button type="button" aria-label="Increase">+</button></div></div>
<div class="pp-desc">{desc or ""}</div>
<div class="pp-note">{NOTE}</div>
</div>
</div>"""


def build_products():
    d = ROOT / "src" / "pages" / PRODUCT_TEMPLATE
    meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
    tpl_d = (d / "desktop.html").read_text(encoding="utf-8")
    tpl_m = (d / "mobile.html").read_text(encoding="utf-8")
    css_dir = ROOT / "product-page"
    css_dir.mkdir(exist_ok=True)
    shutil.copyfile(d / "page.css", css_dir / "product.css")
    old_root = meta["root"]  # template paths were written for product-page/<slug>/
    slugs = sorted(set(PRODUCTS) | set(ITEMS))
    for ps in slugs:
        root = "../../"
        pm = dict(meta)
        name = ITEMS.get(ps, {}).get("name") or PRODUCTS.get(ps, {}).get("name") or ps
        plain = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", DESCRIPTIONS.get(ps, "") or PRODUCTS.get(ps, {}).get("desc", ""))).strip()
        pm["slug"] = "product-page_" + ps
        pm["meta"] = dict(meta["meta"], title=f"{name} | Econ World Trading",
                          description=(plain[:155] + "…") if len(plain) > 155 else plain,
                          og_image=(f"{MEDIA}{ITEMS[ps]['image']}" if ITEMS.get(ps, {}).get("image") else meta["meta"].get("og_image", "")))
        body_d = tpl_d.replace("<!--PRODUCT-->", product_html(ps, root))
        body_m = tpl_m.replace("<!--PRODUCT-->", product_html(ps, root))
        out = ROOT / "product-page" / ps
        out.mkdir(parents=True, exist_ok=True)
        (out / "index.html").write_text(page_html(pm, root, body_d, body_m, ["../product.css"]), encoding="utf-8")
    print(f"wrote {len(slugs)} product pages")


# Pages that are dead or blank on the live site point somewhere useful instead.
REDIRECTS = {
    "online-store": "shop/",  # live site returns a Wix 404 here
    "construction": "prefabricated-prefinished-volumetric-modular-construction/",  # blank page on live site
}


def write_redirect(slug, target):
    out = ROOT / slug
    out.mkdir(parents=True, exist_ok=True)
    for stale in ("page.css",):
        if (out / stale).exists():
            (out / stale).unlink()
    (out / "index.html").write_text(f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>Redirecting…</title>
<link rel="canonical" href="{SITE}/{target}"><meta name="robots" content="noindex">
<meta http-equiv="refresh" content="0; url=../{target}"></head>
<body><p>This page has moved. <a href="../{target}">Continue</a>.</p></body></html>
""", encoding="utf-8")


def write_site_files(slugs):
    pages = [s for s in slugs if s not in REDIRECTS and s != PRODUCT_TEMPLATE]
    urls = [SITE + "/"] + [f"{SITE}/{s}/" for s in pages if s != "home"]
    urls += [f"{SITE}/product-page/{ps}/" for ps in sorted(set(PRODUCTS) | set(ITEMS))]
    (ROOT / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(f"  <url><loc>{u}</loc></url>" for u in urls) + "\n</urlset>\n", encoding="utf-8")
    (ROOT / "robots.txt").write_text(f"User-agent: *\nAllow: /\n\nSitemap: {SITE}/sitemap.xml\n", encoding="utf-8")
    (ROOT / ".nojekyll").write_text("", encoding="utf-8")
    (ROOT / "404.html").write_text("""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Page Not Found | Econ World Trading</title>
<link rel="stylesheet" href="/assets/css/fonts.css">
<style>
body{margin:0;font-family:raleway-semibold,Arial,sans-serif;color:#000;background:#fff}
.wrap{max-width:980px;margin:0 auto;padding:120px 24px;text-align:center}
h1{font-size:50px;margin:0 0 16px}p{font:18px/1.4 proxima-n-w01-reg,Arial,sans-serif;margin:0 0 32px}
a{display:inline-block;background:#282626;color:#fff;text-decoration:none;padding:12px 40px;font:15px/1.4 proxima-n-w01-reg,Arial,sans-serif;letter-spacing:.05em}
a:hover{background:#fff;color:#000;outline:1px solid #000}
</style></head>
<body><div class="wrap"><h1>Page Not Found</h1><p>The page you're looking for isn't available.</p>
<a href="/">Go to Home</a></div></body></html>
""", encoding="utf-8")
    print(f"sitemap: {len(urls)} urls")


def page_html(meta, root, desktop, mobile, css_files):
    e = html.escape
    m = meta["meta"]
    canonical = SITE + "/" + ("" if meta["slug"] == "home" else meta["slug"].replace("product-page_", "product-page/") + "/")
    css_links = "\n".join(f'<link rel="stylesheet" href="{c}">' for c in css_files)
    og = f'<meta property="og:image" content="{e(m["og_image"])}">\n' if m.get("og_image") else ""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1" id="vp">
<script>if(Math.min(screen.width,screen.height)<768)document.getElementById('vp').setAttribute('content','width=320, user-scalable=yes')</script>
<title>{e(m["title"])}</title>
<meta name="description" content="{e(m["description"])}">
<link rel="canonical" href="{canonical}">
<meta property="og:title" content="{e(m["title"])}">
<meta property="og:description" content="{e(m["description"])}">
<meta property="og:url" content="{canonical}">
<meta property="og:type" content="website">
{og}<link rel="icon" sizes="192x192" href="{FAVICON.format(s=192)}" type="image/png">
<link rel="shortcut icon" href="{FAVICON.format(s=32)}" type="image/png">
<link rel="apple-touch-icon" href="{FAVICON.format(s=180)}" type="image/png">
<script>(function(w,d,s,l,i){{w[l]=w[l]||[];w[l].push({{'gtm.start':new Date().getTime(),event:'gtm.js'}});var f=d.getElementsByTagName(s)[0],j=d.createElement(s),dl=l!='dataLayer'?'&l='+l:'';j.async=true;j.src='https://www.googletagmanager.com/gtm.js?id='+i+dl;f.parentNode.insertBefore(j,f);}})(window,document,'script','dataLayer','{GTM}');</script>
<link rel="stylesheet" href="{root}assets/css/fonts.css">
<link rel="stylesheet" href="{root}assets/css/base.css">
{css_links}
</head>
<body>
<noscript><iframe src="https://www.googletagmanager.com/ns.html?id={GTM}" height="0" width="0" style="display:none;visibility:hidden"></iframe></noscript>
<div class="vd">{desktop}</div>
<div class="vm">{mobile}</div>
<script src="{root}assets/js/site.js" defer></script>
</body>
</html>
"""


def main():
    src = ROOT / "src" / "pages"
    slugs = sys.argv[1:] or sorted(p.name for p in src.iterdir() if p.is_dir())
    if PRODUCT_TEMPLATE in slugs or not sys.argv[1:]:
        build_products()
    for slug in slugs:
        if slug == PRODUCT_TEMPLATE:
            continue
        if slug in REDIRECTS:
            write_redirect(slug, REDIRECTS[slug])
            continue
        d = src / slug
        meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
        root = meta["root"]
        out_dir = ROOT if slug == "home" else ROOT / slug.replace("product-page_", "product-page/")
        out_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(d / "page.css", out_dir / "page.css")
        desktop = fill_galleries((d / "desktop.html").read_text(encoding="utf-8"), slug, root)
        mobile = fill_galleries((d / "mobile.html").read_text(encoding="utf-8"), slug, root)
        doc = page_html(meta, root, desktop, mobile, ["page.css"])
        (out_dir / "index.html").write_text(doc, encoding="utf-8")
        print("wrote", out_dir.relative_to(ROOT) / "index.html")


if __name__ == "__main__":
    main()
    if not sys.argv[1:]:
        write_site_files(sorted(p.name for p in (ROOT / "src" / "pages").iterdir() if p.is_dir()))
