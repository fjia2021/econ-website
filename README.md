# econ-website

Static rebuild of [econworldtrading.com](https://www.econworldtrading.com) for hosting on GitHub Pages. Every page keeps the original Wix site's layout, colours, fonts and images. It needs no Wix scripts and no build step to serve.

- **49 pages + 285 product pages**, each with its own desktop layout and its own 320px mobile layout, matching the original. Phones get the mobile layout automatically.
- **Same URLs as the live site** (`/ranges/`, `/product-page/<slug>/`, …), so switching the domain keeps existing links and search rankings working.
- Product grids, product pages, FAQ, mobile menu, search box and forms are rebuilt with plain HTML, CSS and a small `assets/js/site.js`.

## Folder layout

```
index.html, <page>/index.html       finished pages (desktop + mobile layouts in one file)
<page>/page.css                     that page's layout (positions, sizes, colours)
product-page/<slug>/index.html      product pages; product-page/product.css is their shared layout
assets/css/base.css                 shared component styles
assets/css/fonts.css                font mapping (see "Fonts")
assets/fonts/                       font files + licences
assets/js/site.js                   menus, sliders, "Load More", FAQ, quantity stepper
assets/files/                       product catalog PDF
data/                               product catalog: products, grid order, ribbons, descriptions
src/pages/<page>/                   converted page sources the finished pages are assembled from
tools/assemble.py                   rebuilds finished pages from src/ + data/
tools/wix_import.py                 one-time converter that produced src/ from the Wix site
```

## Editing

- **Text or layout on a page:** edit `src/pages/<page>/desktop.html` and/or `mobile.html`, then run `python tools/assemble.py <page>`.
- **Products:** edit the JSON files in `data/` (`products.json`, `descriptions.json`, `galleries.json` for grid order, `gallery_ribbons.json`), then run `python tools/assemble.py`.
- **Preview:** run `python -m http.server 8000` and open http://localhost:8000.

Running `python tools/assemble.py` with no arguments rebuilds every page, plus `sitemap.xml`, `robots.txt` and `404.html`. Python 3.8+ is the only requirement.

## Deploying to GitHub Pages

1. Push this folder to GitHub.
2. Under **Settings → Pages**, choose **Deploy from a branch**, then `main` / root.
3. Under **Custom domain**, enter `www.econworldtrading.com`, then update DNS at the domain registrar. Do this only when you are ready to switch over from Wix.

## Things to know before cancelling Wix

- **Images are still loaded from Wix's image servers** (`static.wixstatic.com`), as is a font the client uploaded to Wix. They stop working if the Wix site is deleted, so download them into the repo first.
- **Forms do not send anything yet.** The contact form, the rebate eligibility form, the "See something you're interested in?" form on Brands, and "Sign Up For Specials" all look the same as the original. On Wix they submitted to Wix's servers. To make them work here they need a form service (for example Formspree) or a backend.
- **Google Tag Manager** (`GTM-PHB4L7GZ`) is included on every page, so analytics and ad tracking continue.

## Fonts

Raleway, Rubik, Poppins and Wix Madefor are the same open-licence fonts the original uses. Proxima Nova, DIN Next, Avenir, Futura and Belinda are licensed by Wix for Wix sites only, so close free equivalents are used instead: Red Hat Text, Barlow, Nunito Sans, Jost and Yellowtail. Licences are in `assets/fonts/licenses/`.

The small icons (help, account, location, phone, email, back-to-top and the five feature icons) are original drawings replacing Wix's icon library, which is licensed for Wix sites only.
