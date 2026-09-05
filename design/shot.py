# Снимок страницы и координаты блоков.
# Нужен, чтобы сверять вёрстку с макетом, а не судить по описанию.
#
#   py design\shot.py                 весь первый экран, 1200
#   py design\shot.py 375             узкий экран
#   py design\shot.py 1200 full       вся страница целиком
#
# Координаты печатаются как [x, y, ширина, высота] относительно окна.
# Чтобы сравнить с макетом, вычесть из них положение карточки.

import sys, pathlib
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "design" / "snapshots"
OUT.mkdir(exist_ok=True)

width = int(sys.argv[1]) if len(sys.argv) > 1 else 1200
full = len(sys.argv) > 2 and sys.argv[2] == "full"

BLOCKS = {
    "card": "header.hero",
    "h1": ".hero h1",
    "photo": ".hero-photo",
    "lead": ".hero .lead",
    "btns": ".hero .btns",
    "facts": ".facts",
}

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": width, "height": 900})
    page.goto(ROOT.joinpath("index.html").as_uri())
    page.wait_for_timeout(2500)          # ждём шрифты с Google Fonts

    name = OUT / f"{'page' if full else 'hero'}-{width}.png"
    if full:
        page.screenshot(path=str(name), full_page=True)
    else:
        page.locator("header.hero").screenshot(path=str(name))
    print("снимок:", name)

    boxes = page.evaluate(
        """(sel) => {
            const out = {};
            for (const [k, s] of Object.entries(sel)) {
                const el = document.querySelector(s);
                if (!el) { out[k] = null; continue; }
                const b = el.getBoundingClientRect();
                out[k] = [Math.round(b.x), Math.round(b.y), Math.round(b.width), Math.round(b.height)];
            }
            out.scrollWidth = document.documentElement.scrollWidth;
            return out;
        }""",
        BLOCKS,
    )
    for k, v in boxes.items():
        print(f"{k:12} {v}")

    # горизонтальная прокрутка это ошибка вёрстки на любой ширине
    if boxes["scrollWidth"] > width:
        print(f"ВНИМАНИЕ: страница шире окна на {boxes['scrollWidth'] - width} точек")

    browser.close()
