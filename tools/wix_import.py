#!/usr/bin/env python3
"""One-time importer: converts saved Wix page HTML into standalone static pages.

Wix renders each page twice (desktop and a separate 320px mobile layout). This
script reads both renders of every page, keeps the site's own design data
(layout positions, sizes, fonts, colours, text, images) and rewrites it as plain
HTML + CSS that runs without Wix. Wix's platform scripts and stylesheets are not
copied; the behaviour they provided is re-implemented in assets/css/base.css.

    python tools/wix_import.py <capture-dir> [slug ...]

<capture-dir> layout (produced by the crawl step, not committed):
    ssr/d/<slug>.html   server HTML, desktop user agent
    ssr/m/<slug>.html   server HTML, mobile user agent
    dom/d/<slug>.html   rendered DOM, desktop   (fills in lazy backgrounds)
    dom/m/<slug>.html   rendered DOM, mobile
"""
import hashlib
import html
import json
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup, Comment, NavigableString, Tag

ROOT = Path(__file__).resolve().parent.parent
SITE = "https://www.econworldtrading.com"
MEDIA = "https://static.wixstatic.com/media/"

KEEP_CLASS = re.compile(r"^(AddressInput|wixui-|font_|color_|comp-|style-|StylableButton|backcolor_|wixGuard|bgImage|mesh-layout|desktop|mobile)")
SKIP_IDS = {"WIX_ADS", "SCROLL_TO_TOP", "SCROLL_TO_BOTTOM", "SKIP_TO_CONTENT_BTN", "soapBeforePagesContainer",
            "soapAfterPagesContainer", "BACKGROUND_GROUP", "CONTROLLER_COMP_CUSTOM_ID", "SITE_BACKGROUND"}
# Wix renders some components with hashed class names; map the ones we re-implement
# to readable names used by assets/css/base.css.
SEM = {
    # classic (non-stylable) button
    "mu5PoX": "sbtn", "twJknM": "sbtn-link", "OR4Nv8": "sbtn-label",
    # header/footer "screen width" container skin
    "CDNoF4": "swskin", "kBvIHj": "sw-bg-wrap", "EaoiSu": "sw-bg", "YmWgf4": "sw-in", "H2MmBb": "sw-center",
    "CmHRsG": "sw-center-bg", "XgJ1FR": "sw-content",
    # header skin
    "MLzr0a": "hskin", "uZIV9d": "hs-bg", "XzOkCb": "hs-layers", "ncI7Xj": "hs-fill", "XKFSfx": "hs-content",
    # slider gallery
    "qF3YMy": "sgal", "tH7trs": "sgal-vis", "JDzwGa": "sgal-items", "YyKeZ9": "sgal-item", "bBF_3m": "gitem",
    "cOMeIx": "gitem-link", "tpXkpl": "gitem-ratio", "HrqFl7": "gitem-a", "woxcJY": "gitem-b", "eEAfCJ": "gitem-img",
    "zfHuGu": "svg-defs",
    "VvZUME": "sgal-prev", "TAdf5r": "sgal-next", "IQBSyl": "sr-only",
    # text input
    "Q1MQrw": "tin", "nuFEsg": "tin-wrap", "nbaJII": "tin-input", "wqbFCn": "tin-prefix", "QyrExM": "tin-label",
    # forms
    "AYCJGp": "wform", "pZqgsf": "tin-haslabel", "TqroEf": "is-required",
    "qa3D4M": "dd", "VYqX7C": "dd-haslabel", "DCgvoa": "is-required", "lo03zG": "dd-label", "UuIgyh": "dd-wrap",
    "Hae_iI": "dd-select", "ztWMYz": "dd-placeholder", "R8pbpf": "dd-arrow", "XiOJeV": "dd-arrow-icon",
    "fRbOAc": "tbox", "bCYfl0": "tbox-haslabel", "edzMuY": "is-required", "P3lL3X": "tbox-label", "XXgBXC": "tbox-input",
    # google map
    "DDi8v8": "gmap",
}
MAP_EMBED = ("https://maps.google.com/maps?q=Econ+World+Trading,+43901+Boscell+Rd,+Fremont,+CA+94538"
             "&z=11&output=embed")

DROP_TAGS = {"script", "noscript", "style", "link", "meta", "template", "title"}
SVG_ATTRS_ALL = True  # svg subtrees are copied verbatim


# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------
def site_css(soup):
    """The site's own generated CSS (layout, component vars, button styles)."""
    out = []
    for st in soup.find_all("style"):
        sid = st.get("id") or ""
        if sid.startswith(("css_", "stylableCss_", "compCssMappers_")):
            out.append(st.string or st.get_text())
    css = "\n".join(out)
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    # Wix-licensed font files are dropped; client-uploaded fonts (ufonts) are kept.
    def font_face(m):
        return m.group(0) if "ufonts" in m.group(0) else ""
    css = re.sub(r"@font-face\s*\{[^}]*\}", font_face, css)
    return css


def split_rules(css):
    """Yield (prelude, body) at top level; nested blocks returned whole."""
    i, n, out = 0, len(css), []
    while i < n:
        j = css.find("{", i)
        if j < 0:
            break
        prelude = css[i:j].strip()
        depth, k = 1, j + 1
        while k < n and depth:
            if css[k] == "{":
                depth += 1
            elif css[k] == "}":
                depth -= 1
            k += 1
        out.append((prelude, css[j + 1:k - 1]))
        i = k
    return out


def scope_selector(sel, scope):
    sel = sel.strip()
    if not sel:
        return sel
    sel = re.sub(r"^(html|:root)\b", scope, sel)
    sel = re.sub(r"^body\b", scope, sel)
    if sel.startswith(scope):
        return sel
    return f"{scope} {sel}"


def scope_css(css, scope):
    out = []
    for prelude, body in split_rules(css):
        if prelude.startswith("@media") or prelude.startswith("@supports") or prelude.startswith("@container"):
            out.append(f"{prelude}{{{scope_css(body, scope)}}}")
        elif prelude.startswith("@"):
            out.append(f"{prelude}{{{body}}}")
        else:
            sels = ",".join(scope_selector(s, scope) for s in split_selectors(prelude))
            out.append(f"{sels}{{{body}}}")
    return "\n".join(out)


def split_selectors(prelude):
    parts, depth, cur = [], 0, ""
    for ch in prelude:
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    parts.append(cur)
    return parts


# ---------------------------------------------------------------------------
# URLs
# ---------------------------------------------------------------------------
def rel_link(href, root):
    if not href:
        return href
    h = href.strip()
    if h.startswith(("tel:", "mailto:", "#", "javascript:")):
        return h
    m = re.match(r"https?://(www\.)?econworldtrading\.com(/[^?#]*)?([?#].*)?$", h)
    if not m:
        return h
    path = (m.group(2) or "/").strip("/")
    if path.startswith("_files/ugd/aabb6a_765c2e01a3114c7094b3e24b22ce6810"):
        return f"{root}assets/files/econ-world-trading-catalog.pdf"  # product catalog, copied off Wix
    if not path:
        return root or "./"
    return f"{root}{path}/"


def media_url(info, w, h):
    data = info.get("imageData", {})
    uri = data.get("uri") or ""
    if not uri:
        return None
    mode = info.get("displayMode") or data.get("displayMode") or "fill"
    crop = data.get("crop")
    w, h = max(1, int(round(w))), max(1, int(round(h)))
    name = uri
    ext = uri.rsplit(".", 1)[-1].lower()
    tail = "q_85,usm_0.66_1.00_0.01,enc_auto" if ext not in ("gif", "svg") else "q_85"
    if crop:
        pre = f"crop/x_{int(crop['x'])},y_{int(crop['y'])},w_{int(crop['width'])},h_{int(crop['height'])}/"
    else:
        pre = ""
    kind = "fit" if mode in ("fit", "legacyFit", "full") else "fill"
    align = "" if kind == "fit" else f",al_{ {'center':'c','top':'t','bottom':'b','left':'l','right':'r','top_left':'tl','top_right':'tr','bottom_left':'bl','bottom_right':'br'}.get(info.get('alignType','center'),'c') }"
    return f"{MEDIA}{uri}/v1/{pre}{kind}/w_{w},h_{h}{align},{tail}/{name}"


def fix_image(wow, img):
    """Swap Wix's blurred placeholder for the real image at 1x/2x."""
    raw = wow.get("data-image-info")
    if not raw or img is None:
        return
    try:
        info = json.loads(raw)
    except ValueError:
        return
    tw = info.get("targetWidth") or img.get("width") or 0
    th = info.get("targetHeight") or img.get("height") or 0
    if not tw or not th:
        data = info.get("imageData", {})
        ow, oh = float(data.get("width") or 0), float(data.get("height") or 0)
        if ow and oh:
            k = min(1.0, 600 / max(ow, oh))
            tw, th = ow * k, oh * k
    try:
        tw, th = float(tw), float(th)
    except (TypeError, ValueError):
        return
    if not tw or not th:
        return
    src1 = media_url(info, tw, th)
    if not src1:
        return
    data = info.get("imageData", {})
    ow, oh = data.get("width") or 99999, data.get("height") or 99999
    scale = min(2.0, ow / tw if tw else 2.0, oh / th if th else 2.0)
    src2 = media_url(info, tw * max(scale, 1), th * max(scale, 1))
    img["src"] = src1
    img["srcset"] = f"{src1} 1x, {src2} 2x" if src2 != src1 else src1
    img["loading"] = "lazy"
    img.attrs.pop("fetchpriority", None)


# ---------------------------------------------------------------------------
# DOM conversion
# ---------------------------------------------------------------------------
# Original icons (24x24 grid) replacing Wix vector-art library icons, keyed by the
# fingerprint of the Wix icon they replace. "stroke" icons are drawn with lines,
# "fill" icons as solid shapes; both take the colour Wix assigned (--fill).
ICONS = {
    "0537157b": ("stroke", '<circle cx="12" cy="12" r="10"/><path d="M9.3 9.2a2.8 2.8 0 1 1 4 2.5c-.9.4-1.3 1-1.3 1.9v.6"/>'
                           '<circle cx="12" cy="17.3" r=".6" fill="currentColor"/>'),                      # help
    "c6f9c917": ("stroke", '<circle cx="12" cy="7.8" r="3.8"/><path d="M4.8 20.5v-1.6a4.9 4.9 0 0 1 4.9-4.9h4.6a4.9 4.9 0 0 1 4.9 4.9v1.6"/>'),  # account
    "f7df3cb6": ("fill", '<path fill-rule="evenodd" d="M12 2.2a6.6 6.6 0 0 0-6.6 6.6c0 4.4 6.6 10.9 6.6 10.9s6.6-6.5 6.6-10.9A6.6 6.6 0 0 0 12 2.2zm0 4.3a2.4 2.4 0 1 1 0 4.8 2.4 2.4 0 0 1 0-4.8z"/>'
                         '<path d="M7.6 17.4c-2.4.5-3.9 1.4-3.9 2.4 0 1.5 3.7 2.6 8.3 2.6s8.3-1.1 8.3-2.6c0-1-1.5-1.9-3.9-2.4l-.5.9c1.6.4 2.6.9 2.6 1.5 0 .9-2.9 1.7-6.5 1.7s-6.5-.8-6.5-1.7c0-.6 1-1.1 2.6-1.5z"/>'),  # location
    "fcf29bbc": ("fill", '<path d="M7.1 2.6 9.4 2c.6-.1 1.1.2 1.3.7l1.3 3.1c.2.5.1 1.1-.4 1.5L10 8.7a12 12 0 0 0 5.3 5.3l1.4-1.6c.4-.4 1-.6 1.5-.4l3.1 1.3c.5.2.8.8.7 1.3l-.6 2.3c-.1.6-.7 1-1.3 1C10.5 17.9 6.1 13.5 6.1 4c0-.6.4-1.2 1-1.4z" transform="translate(-2.1 2)"/>'),  # phone
    "1b8c78d8": ("fill", '<path d="M2.5 6.2A1.7 1.7 0 0 1 4.2 4.5h15.6a1.7 1.7 0 0 1 1.7 1.7v.4L12 12.5 2.5 6.6z"/>'
                         '<path d="M2.5 8.9 12 14.8l9.5-5.9v8.9a1.7 1.7 0 0 1-1.7 1.7H4.2a1.7 1.7 0 0 1-1.7-1.7z"/>'),  # email
    "106319fa": ("stroke", '<circle cx="14.2" cy="12" r="7.6"/><path d="M14.2 7.6V12l3 2.4M1.8 8.6h6M3 12h4.6M1.8 15.4h6"/>'),  # fast service
    "fcda1a32": ("stroke", '<path d="M12 2.4 19.8 5.5v5.8c0 4.8-3.2 8.6-7.8 10.3-4.6-1.7-7.8-5.5-7.8-10.3V5.5z"/>'
                           '<path d="M14.5 9.4c-.3-.9-1.2-1.5-2.5-1.5-1.4 0-2.5.8-2.5 1.9 0 1.2 1 1.6 2.5 1.9s2.6.8 2.6 2c0 1.2-1.1 1.9-2.6 1.9-1.3 0-2.3-.6-2.6-1.6M12 6.4v1.5M12 15.6v1.5"/>'),  # financing
    "67bebb7d": ("stroke", '<path d="M10.2 3.5h7.3v5.6h-7.3zM8.4 9.1h14v7.3h-14zM8.4 11.2H4.6L2 13.9v2.5h6.4"/>'
                           '<circle cx="5.6" cy="17.6" r="1.7"/><circle cx="18.6" cy="17.6" r="1.7"/><path d="M13 3.5v2"/>'),  # delivery
    "3ba4c967": ("stroke", '<path d="M5.2 19.8 14 11M12.4 4.2l4.6 4.6-2 2-4.6-4.6zM10.9 5.7 8.7 3.5 6.8 5.4 9 7.6"/>'
                           '<path d="M19.6 19.6 15.4 15.4M15.4 15.4l-1.6 1.6-1.4-1.4 1.6-1.6zM14.6 14.6 6.3 6.3l-1.9-3.2.8-.8 3.2 1.9 8.3 8.3"/>'),  # installers
    "82620f0d": ("stroke", '<path d="M12 2.2l1.6 1.3 2-.4.9 1.9 1.9.9-.4 2 1.3 1.6-1.3 1.6.4 2-1.9.9-.9 1.9-2-.4L12 16.3l-1.6-1.3-2 .4-.9-1.9-1.9-.9.4-2L4.7 9.2 6 7.6l-.4-2 1.9-.9.9-1.9 2 .4z"/>'
                           '<path d="M9.3 9.4l1.9 1.9 3.6-3.6M8.6 15.6 6.7 21.6l2.6-1.1 1.4 2.3 1.3-6.1M15.4 15.6l1.9 6-2.6-1.1-1.4 2.3-1.3-6.1"/>'),  # quality
    "8e6f3e7e": ("color", '<circle cx="12" cy="12" r="11"/><path d="M7.6 13.8 12 9.4l4.4 4.4"/>'),  # back to top
}


# Tight drawing bounds (incl. half the line width) so icons fill their box like the originals.
ICON_VIEWBOX = {
    "106319fa": "0.9 3.5 21.8 17", "fcda1a32": "3.3 1.5 17.4 21", "67bebb7d": "1.1 2.6 22.2 17.6",
    "3ba4c967": "3.5 1.4 17 19.3", "82620f0d": "3.8 1.3 16.4 22.4",
}


def replace_icon(svg_html):
    """Swap the drawing inside a Wix library icon for an original one, same box and colours."""
    key = hashlib.md5(re.sub(r"\s+", "", svg_html).encode()).hexdigest()[:8]
    if key not in ICONS:
        return svg_html
    kind, body = ICONS[key]
    open_tag = re.match(r"<svg[^>]*>", svg_html).group(0)
    # Wix crops each library icon to its drawing; give ours a tight 24x24 canvas so it fills the box the same way.
    open_tag = re.sub(r'\s(viewbox|data-bbox|preserveaspectratio)="[^"]*"', "", open_tag, flags=re.I)
    open_tag = open_tag[:-1] + f' viewBox="{ICON_VIEWBOX.get(key, "0 0 24 24")}" preserveAspectRatio="xMidYMid meet">'
    tx = ty = 0
    k = 1
    if kind == "color":
        colors = re.findall(r'(?:fill|stroke)="(#[0-9A-Fa-f]{3,6})"', svg_html)
        c1 = colors[0] if colors else "#5E97FF"
        c2 = colors[1] if len(colors) > 1 else c1
        inner = (f'<g transform="translate({tx:.2f} {ty:.2f}) scale({k:.4f})" fill="none" stroke-width="1.6" '
                 f'stroke-linecap="round" stroke-linejoin="round"><g stroke="{c1}">{body.split("<path")[0]}</g>'
                 f'<g stroke="{c2}" stroke-width="1.9"><path{body.split("<path", 1)[1]}</g></g>')
    elif kind == "stroke":
        inner = (f'<g transform="translate({tx:.2f} {ty:.2f}) scale({k:.4f})" style="fill:none;stroke:var(--fill,currentColor);color:var(--fill,currentColor)" '
                 f'stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round">{body}</g>')
    else:
        inner = f'<g transform="translate({tx:.2f} {ty:.2f}) scale({k:.4f})">{body}</g>'
    return open_tag + inner + "</svg>"


class Converter:
    def __init__(self, root_prefix, rendered=None, mobile=False):
        self.r = root_prefix
        self.rendered = rendered
        self.mobile = mobile

    def convert(self, el):
        # Wix Stores product galleries are rebuilt from data at assembly time.
        self.gallery_hosts = {}
        for root in el.find_all(attrs={"data-hook": "gallery-app-root"}):
            host = root.find_parent(lambda t: isinstance(t, Tag) and bool(t.get("id")))
            if host is not None:
                first_page = len(dict.fromkeys(a.get("data-slug") for a in host.find_all(attrs={"data-slug": True})))
                self.gallery_hosts[host["id"]] = (first_page, self.gallery_columns(host["id"]))
        self.faq_hosts = {}
        for root in el.find_all(attrs={"data-hook": "faq-root"}):
            host = root.find_parent(lambda t: isinstance(t, Tag) and bool(t.get("id")))
            if host is not None:
                self.faq_hosts[host["id"]] = root
        self.product_hosts = set()
        for root in el.find_all(attrs={"data-hook": "product-page"}):
            host = root.find_parent(lambda t: isinstance(t, Tag) and bool(t.get("id")))
            if host is not None:
                self.product_hosts.add(host["id"])
        out = []
        self.walk(el, out)
        return "".join(out)

    def classes(self, el):
        raw = el.get("class") or []
        cls = [c for c in raw if KEEP_CLASS.match(c)] + [SEM[c] for c in raw if c in SEM]
        if "PO9MfV" in (el.get("class") or []):
            cls.append("rt-li")
        tid = el.get("data-testid")
        # gallery parts are recognised by their stable test ids, whatever skin is used
        TID_SEM = {"slider-gallery-swipe-left": "sgal-prev", "slider-gallery-swipe-right": "sgal-next",
                   "slider-gallery-visible-items-container": "sgal-vis",
                   "slider-gallery-all-items-container": "sgal-items"}
        if tid in TID_SEM:
            cls.append(TID_SEM[tid])
        if tid and tid.startswith("gallery-item-click-action"):
            cls.append("gitem-link")
        if "wixui-gallery__item" in raw:
            cls += ["gitem", "sgal-item"]
        if "wixui-gallery" in raw and el.find(attrs={"data-testid": "slider-gallery-visible-items-container"}):
            cls.append("sgal")
        if (el.get("id") or "").endswith("-play-button-description"):
            cls.append("sr-only")
        if "wixui-rich-text" in raw and el.get_text(" ", strip=True).lower().startswith("thanks for submitting"):
            cls.append("form-success")
        if el.name == "wow-image" and el.find_parent(class_="wixui-gallery__item"):
            cls.append("gitem-img")
        if tid:
            if tid.startswith("svgRoot"):
                cls.append("svgroot")
            else:
                cls.append("t-" + re.sub(r"[^A-Za-z0-9_-]", "_", tid))
        hook = el.get("data-hook")
        if hook:
            cls.append("h-" + re.sub(r"[^A-Za-z0-9_-]", "_", hook))
        if el.name == "wow-image":
            cls.append("wow-image")
        return cls

    def walk(self, el, out):
        if isinstance(el, Comment):
            return
        if isinstance(el, NavigableString):
            out.append(html.escape(str(el), quote=False))
            return
        if not isinstance(el, Tag):
            return
        name = el.name
        if name in DROP_TAGS:
            return
        eid = el.get("id") or ""
        if eid in SKIP_IDS:
            return
        if name == "svg":
            out.append(self.svg(el))
            return
        if name == "iframe":
            out.append(self.iframe(el))
            return
        if "wixui-google-map" in (el.get("class") or []):
            cls = " ".join(self.classes(el))
            out.append(f'<div id="{eid}" class="{cls}"><iframe class="gmap-frame" title="Map to Econ World Trading" '
                       f'src="{MAP_EMBED}" loading="lazy" referrerpolicy="no-referrer-when-downgrade"></iframe></div>')
            return
        if eid in getattr(self, "faq_hosts", {}):
            cls = " ".join(self.classes(el) + ["faq-host"])
            out.append(f'<div id="{eid}" class="{cls}">{self.faq_widget(self.faq_hosts[eid])}</div>')
            return
        if eid in getattr(self, "product_hosts", set()):
            cls = " ".join(self.classes(el) + ["product-host"])
            out.append(f'<div id="{eid}" class="{cls}"><!--PRODUCT--></div>')
            return
        if eid in getattr(self, "gallery_hosts", {}):
            cls = " ".join(self.classes(el) + ["storegal-host"])
            size, cols = self.gallery_hosts[eid]
            out.append(f'<div id="{eid}" class="{cls}"><!--STOREGAL:{eid}:{size}:{cols}--></div>')
            return
        if name == "fluid-columns-repeater":
            # Wix lays this out with a script and keeps it hidden until then; use flexbox instead.
            hg, vg = el.get("horizontal-gap") or "0", el.get("vertical-gap") or "0"
            jc = el.get("justify-content") or "start"
            out.append(f'<div class="frep" role="list" style="--hgap:{hg}px;--vgap:{vg}px;justify-content:{jc}">')
            for c in el.children:
                self.walk(c, out)
            out.append("</div>")
            return
        if name == "instant-search-input":
            out.append(self.search_box())
            return

        # background media that Wix only fills in after its scripts run
        if eid.startswith("bgMedia_") and not el.find(True) and self.rendered is not None:
            alt = self.rendered.find(id=eid)
            if alt is not None and alt.find(True):
                el = alt

        if name == "wow-image":
            fix_image(el, el.find("img"))
        tag = {"wow-image": "div", "wix-image": "div", "wix-bg-image": "div", "wix-bg-media": "div",
               "wix-video": "div", "custom-element": "div", "interact-element": "div"}.get(name, name)

        attrs = []
        if eid:
            attrs.append(("id", eid))
        cls = self.classes(el)
        if cls:
            attrs.append(("class", " ".join(dict.fromkeys(cls))))
        for a in ("data-mesh-id", "style", "role", "aria-label", "aria-hidden", "title", "alt", "type", "placeholder",
                  "name", "value", "for", "colspan", "rowspan", "width", "height", "target", "rel", "loading", "srcset",
                  "sizes", "dir", "start", "reversed", "data-type", "maxlength", "required", "readonly", "multiple",
                  "selected", "disabled", "checked", "tabindex"):
            v = el.get(a)
            if v is None:
                continue
            if isinstance(v, list):
                v = " ".join(v)
            attrs.append((a, v))
        if name == "img":
            src = el.get("src") or ""
            if src.startswith("data:") and el.get("data-src"):
                src = el["data-src"]
            attrs.append(("src", src))
        if name == "a":
            href = el.get("href")
            if href is None:
                txt = el.get_text(" ", strip=True)
                if re.fullmatch(r"\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}", txt):
                    href = "tel:" + re.sub(r"\D", "", txt)
                elif re.fullmatch(r"[\w.+-]+@[\w-]+\.[\w.]+", txt):
                    href = "mailto:" + txt
            if href is not None:
                attrs.append(("href", rel_link(href, self.r)))
        if name in ("input", "textarea", "select", "button", "form"):
            for a in ("action", "method", "autocomplete", "rows", "cols", "pattern"):
                if el.get(a) is not None:
                    attrs.append((a, el.get(a)))

        attr_s = "".join(f' {k}="{html.escape(str(v), quote=True)}"' for k, v in attrs)
        void = tag in ("img", "input", "br", "hr", "source", "wbr")
        out.append(f"<{tag}{attr_s}>")
        if void:
            return
        for c in el.children:
            self.walk(c, out)
        out.append(f"</{tag}>")

    def faq_widget(self, root):
        """Wix FAQ app rebuilt as tabs + accordion (same texts, same look)."""
        e = html.escape
        title = root.find(attrs={"data-hook": "title"})
        title = title.get_text(" ", strip=True) if title else "Frequently asked questions"
        tabs = [t.get_text(" ", strip=True) for t in root.find_all(attrs={"role": "tab"})] or ["General Questions"]
        items = []
        for head in root.find_all(attrs={"data-hook": "accordion-item-header-content"}):
            item = head.find_parent(lambda t: isinstance(t, Tag) and t.find(attrs={"data-hook": "accordion-item-content"}) is not None)
            body = item.find(attrs={"data-hook": "accordion-item-content"}) if item else None
            ans = ""
            if body is not None:
                frag = BeautifulSoup(str(body), "html.parser")
                for t in frag.find_all(True):
                    t.attrs = {k: v for k, v in t.attrs.items() if k == "href"}
                    if t.name not in ("p", "strong", "b", "em", "i", "u", "br", "ul", "ol", "li", "a", "span"):
                        t.unwrap()
                ans = "".join(str(c) for c in frag.contents)
            items.append((head.get_text(" ", strip=True), ans))
        tab_html = "".join(
            f'<button type="button" role="tab" class="faqw-tab{" is-active" if i == 0 else ""}" '
            f'aria-selected="{"true" if i == 0 else "false"}" data-tab="{i}">{e(t)}</button>'
            for i, t in enumerate(tabs))
        q_html = "".join(
            f'<details class="faqw-item"><summary><span class="faqw-q">{e(q)}</span>'
            f'<span class="faqw-chev" aria-hidden="true"></span></summary><div class="faqw-a">{a}</div></details>'
            for q, a in items)
        lists = f'<div class="faqw-list" data-tab="0">{q_html}</div>' + "".join(
            f'<div class="faqw-list" data-tab="{i}" hidden></div>' for i in range(1, len(tabs)))
        search = ('<label class="faqw-search"><input type="search" placeholder="Looking for something?" '
                  'aria-label="Search questions"><svg viewBox="0 0 24 24" width="19" height="19" aria-hidden="true">'
                  '<circle cx="10.5" cy="10.5" r="6.5" fill="none" stroke="currentColor" stroke-width="1.4"/>'
                  '<line x1="15.3" y1="15.3" x2="20" y2="20" stroke="currentColor" stroke-width="1.4"/></svg></label>')
        return (f'<div class="faqw"><div class="faqw-top"><h2 class="faqw-title">{e(title)}</h2>{search}</div>'
                f'<div class="faqw-tabs" role="tablist">{tab_html}</div>{lists}'
                '<p class="faqw-none" hidden>No results found</p></div>')

    def gallery_columns(self, host_id):
        """Column count from the widget's settings rule (.<host-id> { --galleryColumns: N; ... })."""
        text = getattr(self, "page_text", "")
        for block in re.findall(r"[.#]" + re.escape(host_id) + r"\s*\{([^}]*)\}", text):
            key = r"--mobile-galleryColumns" if self.mobile else r"(?<!mobile-)--galleryColumns"
            m = re.search(key + r":\s*(\d+)", block)
            if m:
                return int(m.group(1))
        return 2 if self.mobile else 3

    def search_box(self):
        """Stand-in for Wix's site-search widget: same look, searches the product catalog."""
        return (f'<form class="ewt-search" role="search" action="{self.r}shop/" method="get">'
                '<input type="search" name="q" placeholder="Search Econ World Trading..." aria-label="Search Econ World Trading">'
                '<button type="submit" aria-label="Search"><svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">'
                '<circle cx="10.5" cy="10.5" r="6.75" fill="none" stroke="currentColor" stroke-width="2"/>'
                '<line x1="15.5" y1="15.5" x2="21" y2="21" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>'
                '</svg></button></form>')

    def svg(self, el):
        if el.find_parent(class_="wixui-gallery__item") and el.get("viewbox", el.get("viewBox")) == "0 0 10000 10000":
            el["class"] = ["gitem-ratio"]
        if el.get("class"):
            raw = el.get("class")
            el["class"] = [c for c in raw if KEEP_CLASS.match(c)] + [SEM[c] for c in raw if c in SEM] or raw
        s = str(el)
        s = re.sub(r"\s*\n\s*", " ", s)
        return replace_icon(s)

    def iframe(self, el):
        src = el.get("src") or el.get("data-src") or ""
        title = el.get("title") or ""
        if not src or src.startswith("about:"):
            return ""
        attrs = f' src="{html.escape(src)}" title="{html.escape(title)}" loading="lazy"'
        for a in ("width", "height", "style", "allow", "allowfullscreen", "scrolling", "frameborder"):
            if el.get(a) is not None:
                attrs += f' {a}="{html.escape(str(el.get(a)))}"'
        return f"<iframe{attrs}></iframe>"


def load(path):
    p = Path(path)
    return BeautifulSoup(p.read_text(encoding="utf-8", errors="replace"), "html.parser") if p.exists() else None


def page_parts(ssr, rendered, root, mobile):
    """Returns (body_html, scoped_css, meta) for one render."""
    scope = ".vm" if mobile else ".vd"
    css = scope_css(site_css(ssr), scope)
    container = ssr.find(id="SITE_CONTAINER")
    conv = Converter(root, rendered, mobile)
    conv.page_text = str(ssr)
    body = conv.convert(container) if container else ""
    return body, css


def head_meta(ssr):
    def meta(attr, key):
        m = ssr.find("meta", attrs={attr: key})
        return m.get("content") if m else ""
    title = ssr.title.get_text() if ssr.title else ""
    return {"title": title, "description": meta("name", "description"), "og_image": meta("property", "og:image"),
            "canonical": (ssr.find("link", rel="canonical") or {}).get("href", "") if ssr.find("link", rel="canonical") else ""}


def main():
    cap = Path(sys.argv[1])
    slugs = sys.argv[2:] or sorted(p.stem for p in (cap / "ssr" / "d").glob("*.html"))
    for slug in slugs:
        sd, sm = load(cap / "ssr/d" / f"{slug}.html"), load(cap / "ssr/m" / f"{slug}.html")
        rd, rm = load(cap / "dom/d" / f"{slug}.html"), load(cap / "dom/m" / f"{slug}.html")
        if sd is None:
            print("missing", slug)
            continue
        out_rel = "index.html" if slug == "home" else f"{slug}/index.html"
        root = "" if slug == "home" else "../" * (slug.count("/") + 1)
        if slug.startswith("product-page_"):
            root = "../../"  # product pages are served from product-page/<slug>/
        dbody, dcss = page_parts(sd, rd, root, False)
        mbody, mcss = page_parts(sm, rm, root, True) if sm is not None else ("", "")
        meta = head_meta(sd)
        data = {"slug": slug, "root": root, "meta": meta}
        dest = ROOT / "src" / "pages" / slug
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "desktop.html").write_text(dbody, encoding="utf-8")
        (dest / "mobile.html").write_text(mbody, encoding="utf-8")
        (dest / "page.css").write_text(dcss + "\n" + mcss, encoding="utf-8")
        (dest / "meta.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{slug}: desktop {len(dbody)//1024}KB, mobile {len(mbody)//1024}KB, css {len((dcss+mcss))//1024}KB")


if __name__ == "__main__":
    main()
