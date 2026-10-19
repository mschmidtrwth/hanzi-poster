#!/usr/bin/env python3
"""
Render data/unified_hanzi.csv as a poster of blocks (character / pinyin / keyword).

Blocks are sorted by HSK level, then by frequency index (Jun Da count, most frequent first; N/A last).
Output is a vector PDF (or SVG/PNG, picked by extension) in ISO 216 proportions.

Examples:
    python poster.py                              # A1 portrait, auto-fit everything on one page
    python poster.py --paper A0 --landscape
    python poster.py --cols 40                    # fix the number of blocks per row
    python poster.py --block-mm 25                # fix block width; spills onto extra pages if needed
    python poster.py --colors "1=#d62828,2=#f77f00" --color-mode text
    python poster.py --break-levels --legend --title "汉字 · HSK"
"""
import argparse
import csv
import math
import sys
from pathlib import Path

import cairo

PAPER_MM = {f"A{i}": (841 / 2 ** (i / 2), 1189 / 2 ** (i / 2)) for i in range(0, 7)}
# Exact ISO 216 values (the formula above rounds slightly differently)
PAPER_MM.update({"A0": (841, 1189), "A1": (594, 841), "A2": (420, 594), "A3": (297, 420),
                 "A4": (210, 297), "A5": (148, 210), "A6": (105, 148)})
MM = 72 / 25.4  # points per mm

NO_LEVEL = 99  # sort key for characters without any HSK level

DEFAULT_COLORS = {
    1: "#4f1b2e",
    2: "#501e0a",
    3: "#283200",
    4: "#00361c",
    5: "#003050",
    6: "#302655",
    7: "#4a1d3d",
    NO_LEVEL: "#666666",
}


def parse_level(unified, individual, source):
    u = int(unified.rsplit("-", 1)[-1]) if unified.strip() else None
    i = int(individual) if individual.strip() else None
    if source == "unified":
        v = u
    elif source == "individual":
        v = i
    else:
        v = min((x for x in (u, i) if x is not None), default=None)
    return NO_LEVEL if v is None else v


def load(path, level_source):
    rows = []
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            freq = r["Jun Da"].strip()
            rows.append({
                "char": r["Character"].strip(),
                "freq": -int(freq) if freq.isdigit() else math.inf,
                "level": parse_level(r["HSK level (unified)"], r["HSK level (individual)"], level_source),
                "pinyin": r["Pinyin"].strip(),
                "meaning": r["Meaning"].strip(),
            })
    rows.sort(key=lambda r: (r["level"], r["freq"], r["char"]))
    return rows


def hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[k:k + 2], 16) / 255 for k in (0, 2, 4))


def mix(c, target, t):
    """Blend colour c towards target by t (0 = c, 1 = target)."""
    return tuple(a + (b - a) * t for a, b in zip(c, target))


def parse_colors(spec):
    colors = dict(DEFAULT_COLORS)
    if spec:
        for part in spec.split(","):
            k, v = part.split("=")
            k = k.strip().lower()
            colors[NO_LEVEL if k in ("none", "-", "0") else int(k)] = v.strip()
    return {k: hex_rgb(v) for k, v in colors.items()}


def layout_slots(rows, cols, break_levels):
    """Assign each row a (grid_row, grid_col) slot. Returns slots and total grid rows."""
    slots, r, c, prev = [], 0, 0, None
    for item in rows:
        if break_levels and prev is not None and item["level"] != prev and c != 0:
            r, c = r + 1, 0
        slots.append((r, c))
        prev = item["level"]
        c += 1
        if c == cols:
            r, c = r + 1, 0
    return slots, r + (1 if c else 0)


def best_fit(rows, avail_w, avail_h, aspect, gap, break_levels):
    """Pick the column count that gives the largest blocks while fitting on one page."""
    best = None
    for cols in range(1, len(rows) + 1):
        _, nrows = layout_slots(rows, cols, break_levels)
        # cols*w + (cols-1)*gap*w <= avail_w, same vertically with block height = w*aspect
        w = min(avail_w / (cols + (cols - 1) * gap),
                avail_h / (nrows * aspect + (nrows - 1) * gap * aspect))
        if best is None or w > best[1]:
            best = (cols, w)
    return best


def fit_font(ctx, text, max_w, size, min_size):
    ctx.set_font_size(size)
    w = ctx.text_extents(text).x_advance
    if w > max_w:
        size = max(min_size, size * max_w / w)
    return size


def draw_text_centered(ctx, text, cx, baseline):
    ext = ctx.text_extents(text)
    ctx.move_to(cx - ext.x_advance / 2, baseline)
    ctx.show_text(text)


def wrap_two(text):
    """Split text into two lines as evenly as possible at a space."""
    words = text.split()
    if len(words) < 2:
        return [text]
    best = min(range(1, len(words)),
               key=lambda k: abs(len(" ".join(words[:k])) - len(" ".join(words[k:]))))
    return [" ".join(words[:best]), " ".join(words[best:])]


def draw_block(ctx, item, x, y, w, h, args, colors):
    base = colors.get(item["level"], colors[NO_LEVEL])
    white, ink = (1, 1, 1), (0.1, 0.1, 0.12)

    if args.color_mode in ("fill", "both"):
        ctx.set_source_rgb(*mix(base, white, args.fill_tint))
        if args.radius > 0:
            r = args.radius * w
            ctx.new_sub_path()
            ctx.arc(x + w - r, y + r, r, -math.pi / 2, 0)
            ctx.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
            ctx.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
            ctx.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
            ctx.close_path()
        else:
            ctx.rectangle(x, y, w, h)
        ctx.fill()

    char_color = base if args.color_mode in ("text", "both") else ink
    if args.color_mode == "both":
        char_color = mix(base, (0, 0, 0), 0.45)  # darken so it reads on the tinted fill
    if args.color_mode == "fill":
        sub_color = (0.25, 0.25, 0.28)
    elif args.color_mode == "both":
        sub_color = char_color
    else:
        sub_color = mix(char_color, white, 0.25)

    cx = x + w / 2
    pad = args.padding * w
    inner_w = w - 2 * pad

    # Vertical bands: character, pinyin, keyword (fractions of block height)
    char_h = args.char_scale * h
    pin_h = args.pinyin_scale * h
    key_h = args.keyword_scale * h
    total = char_h + pin_h + key_h
    top = y + (h - total) / 2

    # Character: em box sized to its band; CJK glyphs sit ~0.88em above baseline in Noto CJK
    ctx.select_font_face(args.char_font, cairo.FONT_SLANT_NORMAL,
                         cairo.FONT_WEIGHT_BOLD if args.char_bold else cairo.FONT_WEIGHT_NORMAL)
    size = min(char_h, inner_w)
    ctx.set_font_size(size)
    ctx.set_source_rgb(*char_color)
    draw_text_centered(ctx, item["char"], cx, top + (char_h - size) / 2 + size * 0.88)

    ctx.select_font_face(args.text_font, cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
    ctx.set_source_rgb(*sub_color)

    # Pinyin
    size = fit_font(ctx, item["pinyin"], inner_w, pin_h * 0.85, pin_h * 0.4)
    ctx.set_font_size(size)
    draw_text_centered(ctx, item["pinyin"], cx, top + char_h + pin_h * 0.5 + size * 0.35)

    # Keyword: shrink to fit; if that gets too small, wrap onto two lines
    nominal = key_h * 0.7
    kw = item["meaning"]
    size = fit_font(ctx, kw, inner_w, nominal, 0)
    lines = [kw]
    if size < nominal * args.wrap_threshold:
        lines = wrap_two(kw)
        size = min(fit_font(ctx, ln, inner_w, nominal, 0) for ln in lines)
        size = min(size, key_h / len(lines) * 0.9)
    ctx.set_font_size(size)
    ky = top + char_h + pin_h
    line_h = key_h / len(lines)
    for n, ln in enumerate(lines):
        draw_text_centered(ctx, ln, cx, ky + line_h * (n + 0.5) + size * 0.35)


def level_name(lv):
    return "no level" if lv == NO_LEVEL else f"HSK {lv}"


def draw_header_footer(ctx, page_w, page_h, margin, args, colors, levels, page, pages):
    ctx.select_font_face(args.text_font, cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
    if args.title:
        ctx.set_source_rgb(0.1, 0.1, 0.12)
        size = args.title_mm * MM
        ctx.set_font_size(size)
        draw_text_centered(ctx, args.title, page_w / 2, margin + size * 0.88)
    if args.legend:
        size = args.legend_mm * MM
        ctx.set_font_size(size)
        sw = size  # swatch size
        items = [(lv, level_name(lv)) for lv in levels]
        widths = [sw * 1.4 + ctx.text_extents(t).x_advance for _, t in items]
        spacing = size * 1.5
        x = (page_w - sum(widths) - spacing * (len(items) - 1)) / 2
        base_y = page_h - margin - size
        for (lv, t), wd in zip(items, widths):
            ctx.set_source_rgb(*colors.get(lv, colors[NO_LEVEL]))
            ctx.rectangle(x, base_y, sw, sw)
            ctx.fill()
            ctx.set_source_rgb(0.2, 0.2, 0.22)
            ctx.move_to(x + sw * 1.4, base_y + sw * 0.85)
            ctx.show_text(t)
            x += wd + spacing
    if pages > 1:
        ctx.set_font_size(3 * MM)
        ctx.set_source_rgb(0.5, 0.5, 0.5)
        t = f"{page}/{pages}"
        ctx.move_to(page_w - margin - ctx.text_extents(t).x_advance, page_h - margin / 2)
        ctx.show_text(t)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("csv", nargs="?", default=str(Path(__file__).resolve().parent / "data" / "unified_hanzi.csv"))
    p.add_argument("-o", "--output", default="hanzi_poster.pdf", help=".pdf, .svg or .png")

    g = p.add_argument_group("page")
    g.add_argument("--paper", default="A1", help="A0–A6, or WxH in mm (e.g. 500x707)")
    g.add_argument("--landscape", action="store_true")
    g.add_argument("--margin-mm", type=float, default=10)
    g.add_argument("--title", default="")
    g.add_argument("--title-mm", type=float, default=18, help="title cap height-ish, in mm")
    g.add_argument("--legend", action="store_true", help="draw a colour legend at the bottom")
    g.add_argument("--legend-mm", type=float, default=6)
    g.add_argument("--png-dpi", type=float, default=150)

    g = p.add_argument_group("grid / block scaling (pick at most one of --cols, --block-mm; default auto-fits one page)")
    g.add_argument("--cols", type=int, help="blocks per row")
    g.add_argument("--block-mm", type=float, help="block width in mm; adds pages as needed")
    g.add_argument("--aspect", type=float, default=1.35, help="block height / width")
    g.add_argument("--gap", type=float, default=0.06, help="gap between blocks, as a fraction of block width")
    g.add_argument("--break-levels", action="store_true", help="start each HSK level on a new row")

    g = p.add_argument_group("block contents")
    g.add_argument("--char-scale", type=float, default=0.62, help="character band, fraction of block height")
    g.add_argument("--pinyin-scale", type=float, default=0.15)
    g.add_argument("--keyword-scale", type=float, default=0.17)
    g.add_argument("--padding", type=float, default=0.05, help="horizontal padding, fraction of block width")
    g.add_argument("--wrap-threshold", type=float, default=0.75,
                   help="wrap keyword onto two lines if shrinking would go below this fraction of nominal size")
    g.add_argument("--char-font", default="Noto Serif CJK SC")
    g.add_argument("--char-bold", action="store_true")
    g.add_argument("--text-font", default="Noto Sans CJK SC")

    g = p.add_argument_group("colour")
    g.add_argument("--colors", help='per level, e.g. "1=#d62828,2=#f77f00,none=#999999"')
    g.add_argument("--color-mode", choices=["fill", "text", "both"], default="fill",
                   help="tint block backgrounds, colour the text, or both")
    g.add_argument("--fill-tint", type=float, default=0.75,
                   help="how far fills are lightened towards white (0 = full colour)")
    g.add_argument("--radius", type=float, default=0.06, help="corner radius, fraction of block width")
    g.add_argument("--level-source", choices=["min", "unified", "individual"], default="min",
                   help="which HSK column to use; 'min' takes the lower of the two")
    g.add_argument("--drop-unleveled", action="store_true", help="leave out characters with no HSK level")
    g.add_argument("--level", type=int, choices=range(1, 8), help="only include characters of this HSK level")
    args = p.parse_args()

    if args.cols and args.block_mm:
        p.error("use either --cols or --block-mm, not both")

    rows = load(args.csv, args.level_source)
    if args.drop_unleveled:
        rows = [r for r in rows if r["level"] != NO_LEVEL]
    if args.level:
        rows = [r for r in rows if r["level"] == args.level]
    colors = parse_colors(args.colors)
    levels = sorted({r["level"] for r in rows})

    if args.paper.upper() in PAPER_MM:
        pw, ph = PAPER_MM[args.paper.upper()]
    else:
        pw, ph = (float(v) for v in args.paper.lower().split("x"))
    if args.landscape:
        pw, ph = ph, pw
    page_w, page_h = pw * MM, ph * MM
    margin = args.margin_mm * MM

    top_reserved = args.title_mm * MM * 1.6 if args.title else 0
    bottom_reserved = args.legend_mm * MM * 2.5 if args.legend else 0
    area_x, area_y = margin, margin + top_reserved
    avail_w = page_w - 2 * margin
    avail_h = page_h - 2 * margin - top_reserved - bottom_reserved

    if args.cols:
        cols = args.cols
        w = avail_w / (cols + (cols - 1) * args.gap)
    elif args.block_mm:
        w = args.block_mm * MM
        cols = max(1, int((avail_w + args.gap * w) // (w * (1 + args.gap))))
    else:
        cols, w = best_fit(rows, avail_w, avail_h, args.aspect, args.gap, args.break_levels)

    h = w * args.aspect
    step_x, step_y = w * (1 + args.gap), h + w * args.gap
    slots, nrows = layout_slots(rows, cols, args.break_levels)
    rows_per_page = max(1, int((avail_h + w * args.gap) // step_y))
    pages = math.ceil(nrows / rows_per_page)

    # Centre the grid in the available area
    grid_w = cols * step_x - w * args.gap
    grid_h = min(nrows, rows_per_page) * step_y - w * args.gap
    off_x = area_x + (avail_w - grid_w) / 2
    off_y = area_y + (avail_h - grid_h) / 2 if pages == 1 else area_y

    ext = args.output.rsplit(".", 1)[-1].lower()
    if ext == "pdf":
        surface = cairo.PDFSurface(args.output, page_w, page_h)
    elif ext == "svg":
        surface = cairo.SVGSurface(args.output, page_w, page_h)
        surface.set_document_unit(cairo.SVGUnit.MM)
    elif ext == "png":
        scale = args.png_dpi / 72
        surface = cairo.ImageSurface(cairo.FORMAT_RGB24, int(page_w * scale), int(page_h * scale))
    else:
        p.error("output must end in .pdf, .svg or .png")
    if ext in ("svg", "png") and pages > 1:
        print(f"warning: {pages} pages needed but {ext} holds one; only page 1 is written", file=sys.stderr)

    ctx = cairo.Context(surface)
    if ext == "png":
        ctx.scale(scale, scale)

    def begin_page(n):
        ctx.set_source_rgb(1, 1, 1)
        ctx.paint()
        draw_header_footer(ctx, page_w, page_h, margin, args, colors, levels, n + 1, pages)

    page = 0
    begin_page(0)
    for item, (r, c) in zip(rows, slots):
        pg = r // rows_per_page
        if pg != page:
            if ext != "pdf":
                break
            ctx.show_page()
            page = pg
            begin_page(page)
        draw_block(ctx, item, off_x + c * step_x, off_y + (r % rows_per_page) * step_y, w, h, args, colors)

    if ext == "png":
        surface.write_to_png(args.output)
    surface.finish()

    print(f"{len(rows)} characters, {cols} cols × {nrows} rows, block {w / MM:.1f}×{h / MM:.1f} mm, "
          f"{pages} page(s) of {pw:.0f}×{ph:.0f} mm → {args.output}")


if __name__ == "__main__":
    main()
