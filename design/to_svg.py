# Снимает блок страницы и собирает из него редактируемый SVG:
# текст остаётся текстом, фон и кнопки прямоугольниками, картинки зашиваются в файл.
#
#   py design\to_svg.py <селектор> <имя файла> [ширина окна]
#
# Например:
#   py design\to_svg.py "header.hero" mobile-hero 375
#   py design\to_svg.py "#about"      mobile-about 375
#
# Готовые файлы кладутся в design/. Открывать в Figma, Illustrator, Inkscape.

import sys, base64, pathlib, mimetypes, html
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent

JS = r"""
(sel) => {
  const root = document.querySelector(sel);
  const base = root.getBoundingClientRect();
  const cv = document.createElement('canvas').getContext('2d');
  const boxes = [], texts = [], images = [], lines = [];

  const walk = (el) => {
    const cs = getComputedStyle(el);
    const r = el.getBoundingClientRect();
    if (cs.display === 'none' || r.width === 0) return;

    // подложка
    const bg = cs.backgroundColor;
    if (bg && bg !== 'rgba(0, 0, 0, 0)' && bg !== 'transparent') {
      boxes.push({x: r.x - base.x, y: r.y - base.y, w: r.width, h: r.height,
                  fill: bg, rx: parseFloat(cs.borderTopLeftRadius) || 0,
                  stroke: null});
    }
    // обводка кнопок
    const bw = parseFloat(cs.borderTopWidth) || 0;
    if (bw > 0 && cs.borderTopStyle === 'solid') {
      const isFrame = (parseFloat(cs.borderBottomWidth) || 0) > 0;
      if (isFrame) {
        boxes.push({x: r.x - base.x, y: r.y - base.y, w: r.width, h: r.height,
                    fill: 'none', rx: parseFloat(cs.borderTopLeftRadius) || 0,
                    stroke: cs.borderTopColor, sw: bw});
      } else {
        lines.push({x1: r.x - base.x, y1: r.y - base.y,
                    x2: r.x + r.width - base.x, y2: r.y - base.y,
                    stroke: cs.borderTopColor, sw: bw});
      }
    }
    if (el.tagName === 'IMG') {
      images.push({x: r.x - base.x, y: r.y - base.y, w: r.width, h: r.height,
                   src: el.getAttribute('src'), transform: cs.transform,
                   origin: cs.transformOrigin});
      return;
    }

    for (const node of el.childNodes) {
      if (node.nodeType === 1) walk(node);
      else if (node.nodeType === 3 && node.textContent.trim()) {
        const t = node.textContent;
        const range = document.createRange();
        cv.font = cs.fontStyle + ' ' + cs.fontWeight + ' ' + cs.fontSize + ' ' + cs.fontFamily;
        const m = cv.measureText('Нх');
        const asc = m.fontBoundingBoxAscent, desc = m.fontBoundingBoxDescent;
        const lh = parseFloat(cs.lineHeight) || (parseFloat(cs.fontSize) * 1.4);
        const half = (lh - (asc + desc)) / 2;

        // режем текстовый узел на строки по положению символов
        let start = 0, prevTop = null, buf = '', left = null;
        const flush = (end, top) => {
          const s = t.slice(start, end).trim();
          if (s) texts.push({x: left - base.x, y: top - base.y + half + asc, text: s,
                             size: parseFloat(cs.fontSize), family: cs.fontFamily,
                             weight: cs.fontWeight, fill: cs.color,
                             spacing: parseFloat(cs.letterSpacing) || 0,
                             upper: cs.textTransform === 'uppercase'});
        };
        for (let i = 0; i < t.length; i++) {
          range.setStart(node, i); range.setEnd(node, i + 1);
          const rr = range.getBoundingClientRect();
          if (rr.width === 0 && rr.height === 0) continue;
          if (prevTop === null) { prevTop = rr.top; left = rr.left; }
          else if (Math.abs(rr.top - prevTop) > 2) {
            flush(i, prevTop); start = i; prevTop = rr.top; left = rr.left;
          }
        }
        if (prevTop !== null) flush(t.length, prevTop);
      }
    }
  };
  walk(root);
  return {w: base.width, h: base.height, boxes, texts, images, lines,
          page: getComputedStyle(document.body).backgroundColor};
}
"""


def esc(s):
    return html.escape(s, quote=False)


def build(data, out_path):
    W, H = round(data["w"]), round(data["h"])
    p = [f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
         f'width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
         f'  <rect width="{W}" height="{H}" fill="{data["page"]}"/>']

    for b in data["boxes"]:
        # у пилюль радиус 999, в SVG его надо ограничить половиной стороны
        r = min(b["rx"], b["w"] / 2, b["h"] / 2)
        rx = f' rx="{r:.0f}"' if r else ""
        stroke = f' stroke="{b["stroke"]}" stroke-width="{b.get("sw", 1):.1f}"' if b["stroke"] else ""
        p.append(f'  <rect x="{b["x"]:.1f}" y="{b["y"]:.1f}" width="{b["w"]:.1f}" '
                 f'height="{b["h"]:.1f}"{rx} fill="{b["fill"]}"{stroke}/>')

    for im in data["images"]:
        src = ROOT / im["src"]
        mime = mimetypes.guess_type(src.name)[0] or "image/png"
        b64 = base64.b64encode(src.read_bytes()).decode()
        tr = ""
        if im["transform"] and im["transform"] != "none":
            ox, oy = (im["origin"] or "0px 0px").split()[:2]
            tr = (f' transform="translate({im["x"]:.1f} {im["y"]:.1f}) '
                  f'translate({float(ox[:-2]):.1f} {float(oy[:-2]):.1f}) '
                  f'matrix({im["transform"][7:-1]}) '
                  f'translate({-float(ox[:-2]):.1f} {-float(oy[:-2]):.1f})"')
            p.append(f'  <image x="0" y="0" width="{im["w"]:.1f}" height="{im["h"]:.1f}"{tr} '
                     f'xlink:href="data:{mime};base64,{b64}"/>')
        else:
            p.append(f'  <image x="{im["x"]:.1f}" y="{im["y"]:.1f}" width="{im["w"]:.1f}" '
                     f'height="{im["h"]:.1f}" xlink:href="data:{mime};base64,{b64}"/>')

    for l in data["lines"]:
        p.append(f'  <line x1="{l["x1"]:.1f}" y1="{l["y1"]:.1f}" x2="{l["x2"]:.1f}" '
                 f'y2="{l["y2"]:.1f}" stroke="{l["stroke"]}" stroke-width="{l["sw"]:.1f}"/>')

    for t in data["texts"]:
        fam = t["family"].split(",")[0].strip("'\" ")
        sp = f' letter-spacing="{t["spacing"]:.2f}"' if t["spacing"] else ""
        # text-transform не меняет содержимое узла, поднимаем регистр сами
        if t["upper"]:
            t["text"] = t["text"].upper()
        p.append(f'  <text x="{t["x"]:.1f}" y="{t["y"]:.1f}" font-family="{esc(fam)}" '
                 f'font-size="{t["size"]:.1f}" font-weight="{t["weight"]}" '
                 f'fill="{t["fill"]}"{sp}>{esc(t["text"])}</text>')

    p.append("</svg>\n")
    out_path.write_text("\n".join(p), encoding="utf-8")
    kb = out_path.stat().st_size / 1024
    print(f"{out_path.name}: {W}x{H}, {kb:.0f} КБ, "
          f"текстовых строк {len(data['texts'])}, картинок {len(data['images'])}")


def main():
    sel, name = sys.argv[1], sys.argv[2]
    width = int(sys.argv[3]) if len(sys.argv) > 3 else 375
    with sync_playwright() as pw:
        br = pw.chromium.launch()
        pg = br.new_page(viewport={"width": width, "height": 900})
        pg.goto(ROOT.joinpath("index.html").as_uri())
        pg.wait_for_timeout(2500)
        data = pg.evaluate(JS, sel)
        br.close()
    build(data, ROOT / "design" / f"{name}.svg")


main()
