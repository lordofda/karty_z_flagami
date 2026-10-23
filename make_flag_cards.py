#!/usr/bin/env python3
"""
make_flag_cards.py - printable two-sided country flag cards.

Front of each card: the national flag (downloaded from flagcdn.com / flagi-panstw.pl CDN).
Back of each card:  the country name in Polish.

Cards are laid out as contact sheets (a grid of cards) on A4/A3 paper so they can
be printed duplex and cut out with scissors.

Dependencies:
    pip install reportlab pillow

Usage examples:
    # everything, both A4 and A3 sheets, long-edge duplex
    python3 make_flag_cards.py

    # just a few countries, A4, 50x70mm cards, plus single card PNGs
    python3 make_flag_cards.py --only pl de fr it --papers A4 --card 50x70 --emit both
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

CDN = "https://flagcdn.com"
MM = 72.0 / 25.4  # millimetres -> PDF points

PAPER_SIZES_MM = {
    "A3": (297.0, 420.0),
    "A4": (210.0, 297.0),
    "A5": (148.0, 210.0),
    "Letter": (215.9, 279.4),
}

# 195 sovereign states: 193 UN members + 2 UN observers (VA, PS).
SOVEREIGN = """
ad ae af ag al am ao ar at au az ba bb bd be bf bg bh bi bj bn bo br bs bt bw by bz
ca cd cf cg ch ci cl cm cn co cr cu cv cy cz de dj dk dm do dz ec ee eg er es et fi fj fm fr
ga gb gd ge gh gm gn gq gr gt gw gy hr ht hu id ie il in iq ir is it jm jo jp ke kg kh ki km kn
kp kr kw kz la lb lc li lk lr ls lt lu lv ly ma mc md me mg mh mk ml mm mn mr ms mt mu mv mw mx
my mz na ne ng ni nl no np nr nz om pa pe pg ph pk pl ps pt pw py qa ro rs ru rw sa sb sc sd
se sg si sk sl sm sn so sr ss st sv sy sz td tg th tj tl tm tn to tr tt tv tz ua ug us uy uz
va vc ve vn vu ws ye za zm zw
""".split()

FONT_CANDIDATES_REGULAR = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "C:/Windows/Fonts/arial.ttf",
]
FONT_CANDIDATES_BOLD = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
]

FONT_SIZE_MIN_PT = 7.0
LINE_SPACING = 1.22
CARD_BORDER_COLOR = (0.78, 0.78, 0.80)
CARD_BORDER_WIDTH = 0.4
TEXT_COLOR = (0.10, 0.10, 0.12)
CODE_COLOR = (0.55, 0.55, 0.58)
BAND_HEIGHT_MM = 6.5

# Kontynent -> (etykieta po polsku, kolor RGB 0..1)
CONTINENT_STYLE = {
    "europa": ("Europa", (0.78, 0.06, 0.18)),          # czerwony
    "afryka": ("Afryka", (0.96, 0.51, 0.13)),           # pomarańczowy
    "ameryka-polnocna": ("Ameryka Północna", (0.00, 0.45, 0.81)),   # niebieski
    "ameryka-poludniowa": ("Ameryka Południowa", (0.00, 0.45, 0.81)),  # niebieski
    "azja": ("Azja", (0.16, 0.49, 0.21)),               # zielony
    "australia": ("Australia i Oceania", (0.47, 0.11, 0.23)),         # bordowy
    "inne": ("Antarktyka i pozostałe", (0.47, 0.11, 0.23)),           # bordowy
}

# Kod ISO 3166-1 -> grupa kontynentu (zródło: flagi-panstw.pl/kontynent)
CONTINENT_BY_CODE = {
    "ad": "europa", "ae": "azja", "af": "azja", "ag": "ameryka-polnocna", "ai": "ameryka-polnocna", "al": "europa",
    "am": "azja", "ao": "afryka", "aq": "inne", "ar": "ameryka-poludniowa", "as": "australia", "at": "europa",
    "au": "australia", "aw": "ameryka-polnocna", "ax": "europa", "az": "azja", "ba": "europa", "bb": "ameryka-polnocna",
    "bc": "ameryka-polnocna", "bd": "azja", "be": "europa", "bf": "afryka", "bg": "europa", "bh": "azja",
    "bi": "afryka", "bj": "afryka", "bl": "ameryka-polnocna", "bm": "ameryka-polnocna", "bn": "azja", "bo": "ameryka-poludniowa",
    "bq": "ameryka-polnocna", "br": "ameryka-poludniowa", "bs": "ameryka-polnocna", "bt": "azja", "bv": "inne",
    "bw": "afryka", "by": "europa", "bz": "ameryka-polnocna", "ca": "ameryka-polnocna", "cc": "australia", "cd": "afryka",
    "cf": "afryka", "cg": "afryka", "ch": "europa", "ci": "afryka", "ck": "australia", "cl": "ameryka-poludniowa",
    "cm": "afryka", "cn": "azja", "co": "ameryka-poludniowa", "cr": "ameryka-polnocna", "cu": "ameryka-polnocna",
    "cv": "afryka", "cw": "ameryka-polnocna", "cx": "australia", "cy": "europa", "cz": "europa", "de": "europa",
    "dj": "afryka", "dk": "europa", "dm": "ameryka-polnocna", "do": "ameryka-polnocna", "dz": "afryka", "ec": "ameryka-poludniowa",
    "ee": "europa", "eg": "afryka", "eh": "afryka", "er": "afryka", "es": "europa", "et": "afryka", "eu": "inne",
    "fi": "europa", "fj": "australia", "fk": "ameryka-poludniowa", "fm": "australia", "fo": "europa", "fr": "europa",
    "ga": "afryka", "gb": "europa", "gd": "ameryka-polnocna", "ge": "azja", "gf": "ameryka-poludniowa", "gg": "europa",
    "gh": "afryka", "gi": "europa", "gl": "ameryka-polnocna", "gm": "afryka", "gn": "afryka", "gp": "ameryka-polnocna",
    "gq": "afryka", "gr": "europa", "gt": "ameryka-polnocna", "gu": "australia", "gw": "afryka", "gy": "ameryka-poludniowa",
    "hk": "azja", "hm": "inne", "hn": "ameryka-polnocna", "hr": "europa", "ht": "ameryka-polnocna", "hu": "europa",
    "id": "australia", "ie": "europa", "il": "azja", "im": "europa", "in": "azja", "io": "afryka", "iq": "azja",
    "ir": "azja", "is": "europa", "it": "europa", "je": "europa", "jm": "ameryka-polnocna", "jo": "azja", "jp": "azja",
    "ke": "afryka", "kg": "azja", "kh": "azja", "ki": "australia", "km": "afryka", "kn": "ameryka-polnocna", "kp": "azja",
    "kr": "azja", "kw": "azja", "ky": "ameryka-polnocna", "kz": "azja", "la": "azja", "lb": "azja", "lc": "ameryka-polnocna",
    "li": "europa", "lk": "azja", "lr": "afryka", "ls": "afryka", "lt": "europa", "lu": "europa", "lv": "europa",
    "ly": "afryka", "ma": "afryka", "mc": "europa", "md": "europa", "me": "europa", "mg": "afryka", "mh": "australia",
    "mk": "europa", "ml": "afryka", "mm": "azja", "mn": "azja", "mo": "azja", "mp": "australia", "mq": "ameryka-polnocna",
    "mr": "afryka", "ms": "ameryka-polnocna", "mt": "europa", "mu": "afryka", "mv": "azja", "mw": "afryka", "mx": "ameryka-polnocna",
    "my": "azja", "mz": "afryka", "na": "afryka", "nc": "australia", "ne": "afryka", "nf": "australia", "ng": "afryka",
    "ni": "ameryka-polnocna", "nl": "europa", "no": "europa", "np": "azja", "nr": "australia", "nu": "australia",
    "nz": "australia", "om": "azja", "pa": "ameryka-polnocna", "pe": "ameryka-poludniowa", "pf": "australia",
    "pg": "australia", "ph": "azja", "pk": "azja", "pl": "europa", "pm": "ameryka-polnocna", "pn": "australia",
    "pr": "ameryka-polnocna", "ps": "azja", "pt": "europa", "pw": "australia", "py": "ameryka-poludniowa", "qa": "azja",
    "re": "afryka", "ro": "europa", "rs": "europa", "ru": "azja", "rw": "afryka", "sa": "azja", "sb": "australia",
    "sc": "afryka", "sd": "afryka", "se": "europa", "sg": "azja", "sh": "afryka", "si": "europa", "sj": "europa",
    "sk": "europa", "sl": "afryka", "sm": "europa", "sn": "afryka", "so": "afryka", "sr": "ameryka-poludniowa",
    "ss": "afryka", "st": "afryka", "sv": "ameryka-polnocna", "sx": "ameryka-polnocna", "sy": "azja", "sz": "afryka",
    "tc": "ameryka-polnocna", "td": "afryka", "tg": "afryka", "th": "azja", "tj": "azja", "tk": "australia",
    "tl": "azja", "tm": "azja", "tn": "afryka", "to": "australia", "tr": "azja", "tt": "ameryka-poludniowa",
    "tv": "australia", "tw": "azja", "tz": "afryka", "ua": "europa", "ug": "afryka", "um": "ameryka-polnocna",
    "un": "inne", "us": "ameryka-polnocna", "uy": "ameryka-poludniowa", "uz": "azja", "va": "europa",
    "vc": "ameryka-polnocna", "ve": "ameryka-poludniowa", "vg": "ameryka-polnocna", "vi": "ameryka-polnocna",
    "vn": "azja", "vu": "australia", "wf": "australia", "ws": "australia", "ye": "azja", "yt": "afryka",
    "za": "afryka", "zm": "afryka", "zw": "afryka",
}


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #


@dataclass
class Card:
    code: str
    name: str
    continent: str  # klucz grupy kontynentu
    sheet: int
    row: int
    col: int
    x: float  # mm, left edge on the sheet
    y: float  # mm, bottom edge on the sheet


@dataclass
class Grid:
    """Placement of cards on one paper size."""

    paper: str
    page_w: float
    page_h: float
    card_w: float
    card_h: float
    cols: int
    rows: int
    origin_x: float
    origin_y: float
    cards: list[Card] = field(default_factory=list)

    @property
    def per_sheet(self) -> int:
        return self.cols * self.rows


# --------------------------------------------------------------------------- #
# Networking
# --------------------------------------------------------------------------- #


def fetch_json(url: str, retries: int = 4, timeout: int = 30) -> dict:
    last = None
    for _ in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "make_flag_cards/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            last = exc
    raise RuntimeError(f"Nie udało się pobrać {url}: {last}")


def fetch_bytes(url: str, retries: int = 4, timeout: int = 60) -> bytes:
    last = None
    for _ in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "make_flag_cards/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except Exception as exc:  # noqa: BLE001
            last = exc
    raise RuntimeError(f"Nie udało się pobrać {url}: {last}")


def download_flags(codes: list[str], cache_dir: Path, width: int, workers: int = 8) -> dict[str, Path]:
    """Download flag PNGs into cache_dir (cached between runs). Returns code -> path."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    todo: list[str] = []

    for code in codes:
        path = cache_dir / f"{code}.png"
        if path.exists() and path.stat().st_size > 0:
            paths[code] = path
        else:
            todo.append(code)

    if not todo:
        return paths

    print(f"Pobieranie {len(todo)} flag (z cache: {len(paths)})…", file=sys.stderr)
    failures: list[tuple[str, str]] = []

    def grab(code: str) -> tuple[str, str | None]:
        url = f"{CDN}/w{width}/{code}.png"
        try:
            data = fetch_bytes(url)
            if not data.startswith(b"\x89PNG"):
                raise RuntimeError("odpowiedź nie jest plikiem PNG")
            dest = cache_dir / f"{code}.png"
            tmp = dest.with_suffix(".png.part")
            tmp.write_bytes(data)
            tmp.replace(dest)
            return code, None
        except Exception as exc:  # noqa: BLE001
            return code, str(exc)

    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for code, err in pool.map(grab, todo):
            done += 1
            if err:
                failures.append((code, err))
            else:
                paths[code] = cache_dir / f"{code}.png"
            if done % 25 == 0 or done == len(todo):
                print(f"  … {done}/{len(todo)}", file=sys.stderr)

    if failures:
        print(f"  ⚠ nie pobrano {len(failures)} flag:", file=sys.stderr)
        for code, err in failures[:10]:
            print(f"    {code}: {err}", file=sys.stderr)
    return paths


# --------------------------------------------------------------------------- #
# Layout
# --------------------------------------------------------------------------- #


def build_grid(
    paper: str,
    card_w: float,
    card_h: float,
    margin: float,
    codes: list[str],
    names: dict[str, str],
    mirror_long: bool = False,
    mirror_short: bool = False,
) -> Grid:
    page_w, page_h = PAPER_SIZES_MM[paper]
    cols = max(1, int((page_w - 2 * margin) // card_w))
    rows = max(1, int((page_h - 2 * margin) // card_h))
    origin_x = (page_w - cols * card_w) / 2.0
    origin_y = (page_h - rows * card_h) / 2.0

    per_sheet = cols * rows
    cards: list[Card] = []
    for index, code in enumerate(codes):
        slot = index % per_sheet
        sheet = index // per_sheet
        row, col = divmod(slot, cols)

        # The back side must line up with the front once the paper is flipped:
        # a long-edge flip mirrors horizontally, a short-edge flip vertically.
        back_col = cols - 1 - col if mirror_long else col
        back_row = rows - 1 - row if mirror_short else row

        cards.append(
            Card(
                code=code,
                name=names.get(code, code.upper()),
                continent=CONTINENT_BY_CODE.get(code, "inne"),
                sheet=sheet,
                row=back_row,
                col=back_col,
                x=origin_x + back_col * card_w,
                y=origin_y + back_row * card_h,
            )
        )

    return Grid(
        paper=paper,
        page_w=page_w,
        page_h=page_h,
        card_w=card_w,
        card_h=card_h,
        cols=cols,
        rows=rows,
        origin_x=origin_x,
        origin_y=origin_y,
        cards=cards,
    )


# --------------------------------------------------------------------------- #
# Text helpers
# --------------------------------------------------------------------------- #


def wrap_to_width(text: str, measure, max_width: float, size: float) -> list[str]:
    """Greedy word wrap. `measure(text, size) -> width`."""
    words = text.split()
    if not words:
        return [""]
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if measure(candidate, size) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def split_long_word(word: str, measure, max_width: float, size: float) -> list[str]:
    """Hard-split a word that cannot fit on a single line."""
    if measure(word, size) <= max_width:
        return [word]
    parts: list[str] = []
    current = ""
    for ch in word:
        candidate = current + ch
        if current and measure(candidate, size) > max_width:
            parts.append(current)
            current = ch
        else:
            current = candidate
    if current:
        parts.append(current)
    return parts


def fit_text(text: str, measure, max_width: float, max_height: float, start_size: float,
             min_size: float = FONT_SIZE_MIN_PT) -> tuple[list[str], float]:
    """Largest font size (<= start_size) whose wrapped text fits the box.

    Shrinks until the block fits vertically *and* the longest single word fits
    horizontally (long Polish compounds are not breakable at spaces).
    """
    size = start_size
    while True:
        lines = wrap_to_width(text, measure, max_width, size)
        fits_height = len(lines) * size * LINE_SPACING <= max_height
        words = text.split()
        longest = max(words, key=lambda w: measure(w, size), default="")
        fits_width = not longest or measure(longest, size) <= max_width
        if size <= min_size or (fits_height and fits_width):
            break
        size = max(min_size, size - 0.5)

    # Fallback: the word still does not fit -> split it by characters.
    broken: list[str] = []
    for line in lines:
        for word in line.split():
            broken.extend(split_long_word(word, measure, max_width, size))
    # re-wrap the broken pieces
    out: list[str] = []
    current = ""
    for piece in broken:
        candidate = f"{current} {piece}" if current else piece
        if current and measure(candidate, size) > max_width:
            out.append(current)
            current = piece
        else:
            current = candidate
    if current:
        out.append(current)
    return (out or lines), size


# --------------------------------------------------------------------------- #
# PDF output
# --------------------------------------------------------------------------- #


def make_pdf(
    grid: Grid,
    side: str,  # "front" | "back"
    flag_paths: dict[str, Path],
    out_path: Path,
    padding: float,
    show_code: bool,
    show_continent: bool,
    draw_borders: bool,
    font_regular: str | None,
    font_bold: str | None,
    title: str,
) -> int:
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas as pdfcanvas

    if font_regular and font_bold:
        pdfmetrics.registerFont(TTFont("CardSans", font_regular))
        pdfmetrics.registerFont(TTFont("CardSans-Bold", font_bold))
        font_name, bold_name = "CardSans", "CardSans-Bold"
    else:
        font_name = bold_name = "Helvetica"

    def measure(text: str, size: float) -> float:
        return pdfmetrics.stringWidth(text, bold_name, size)

    page_w_pt = grid.page_w * MM
    page_h_pt = grid.page_h * MM
    c = pdfcanvas.Canvas(str(out_path), pagesize=(page_w_pt, page_h_pt))
    c.setTitle(title)
    c.setCreator("make_flag_cards.py")

    total_sheets = max((card.sheet for card in grid.cards), default=-1) + 1
    for sheet in range(total_sheets):
        c.setPageSize((page_w_pt, page_h_pt))
        for card in (card for card in grid.cards if card.sheet == sheet):
            x_pt = card.x * MM
            y_pt = card.y * MM
            w_pt = grid.card_w * MM
            h_pt = grid.card_h * MM

            if draw_borders:
                c.setStrokeColorRGB(*CARD_BORDER_COLOR)
                c.setLineWidth(CARD_BORDER_WIDTH)
                c.rect(x_pt, y_pt, w_pt, h_pt, stroke=1, fill=0)

            pad = padding * MM
            inner_x = x_pt + pad
            inner_y = y_pt + pad
            inner_w = w_pt - 2 * pad
            inner_h = h_pt - 2 * pad

            if side == "front":
                path = flag_paths.get(card.code)
                if path is None:
                    continue
                img = ImageReader(str(path))
                iw, ih = img.getSize()
                if iw <= 0 or ih <= 0:
                    continue
                scale = min(inner_w / iw, inner_h / ih)
                dw, dh = iw * scale, ih * scale
                c.drawImage(
                    img,
                    inner_x + (inner_w - dw) / 2.0,
                    inner_y + (inner_h - dh) / 2.0,
                    width=dw,
                    height=dh,
                )
            else:
                cont_key = card.continent if show_continent else None
                cont_label, cont_color = (
                    CONTINENT_STYLE.get(cont_key, ("", (0.5, 0.5, 0.5)))
                    if cont_key
                    else ("", (0.5, 0.5, 0.5))
                )
                band_h = BAND_HEIGHT_MM * MM if cont_key else 0.0
                code_h = 9 * MM if show_code else 0.0

                if cont_key:
                    c.setFillColorRGB(*cont_color)
                    c.rect(inner_x, inner_y, inner_w, band_h, stroke=0, fill=1)

                text_bottom = inner_y + band_h
                text_h = inner_h - band_h - code_h
                start_size = min(grid.card_h * 0.30, grid.card_w * 0.13) * MM
                lines, size = fit_text(card.name, measure, inner_w, text_h, start_size)
                total = len(lines) * size * LINE_SPACING
                ty = text_bottom + (text_h - total) / 2.0 + total - size
                c.setFillColorRGB(*TEXT_COLOR)
                c.setFont(bold_name, size)
                for line in lines:
                    tw = pdfmetrics.stringWidth(line, bold_name, size)
                    c.drawString(inner_x + (inner_w - tw) / 2.0, ty, line)
                    ty -= size * LINE_SPACING

                if cont_key:
                    band_size = min(8.0, band_h * 0.62)
                    c.setFillColorRGB(1, 1, 1)
                    c.setFont(bold_name, band_size)
                    tw = pdfmetrics.stringWidth(cont_label, bold_name, band_size)
                    c.drawString(
                        inner_x + (inner_w - tw) / 2.0,
                        inner_y + (band_h - band_size) / 2.0 + band_size * 0.22,
                        cont_label,
                    )

                if show_code:
                    c.setFillColorRGB(*CODE_COLOR)
                    c.setFont(font_name, 6.5)
                    c.drawString(inner_x, inner_y + inner_h - code_h, card.code.upper())
        c.showPage()

    c.save()
    return total_sheets


# --------------------------------------------------------------------------- #
# PNG output (single cards)
# --------------------------------------------------------------------------- #


def make_card_pngs(
    cards: list[Card],
    flag_paths: dict[str, Path],
    out_dir: Path,
    card_w_mm: float,
    card_h_mm: float,
    dpi: int,
    padding: float,
    show_code: bool,
    show_continent: bool,
    font_regular: str | None,
    font_bold: str | None,
) -> None:
    from PIL import Image, ImageDraw, ImageFont

    px_per_mm = dpi / 25.4
    W = int(round(card_w_mm * px_per_mm))
    H = int(round(card_h_mm * px_per_mm))
    pad = int(round(padding * px_per_mm))
    band_h = int(round(BAND_HEIGHT_MM * px_per_mm))
    out_dir.mkdir(parents=True, exist_ok=True)

    def load(path: str | None, size: int):
        if path:
            return ImageFont.truetype(path, size)
        return ImageFont.load_default()

    for card in cards:
        cont_key = card.continent if show_continent else None
        cont_label, cont_color = (
            CONTINENT_STYLE.get(cont_key, ("", (128, 128, 128))) if cont_key else ("", (128, 128, 128))
        )
        for side in ("front", "back"):
            img = Image.new("RGB", (W, H), "white")
            draw = ImageDraw.Draw(img)

            if side == "front":
                path = flag_paths.get(card.code)
                if path is None:
                    continue
                with Image.open(path) as src:
                    if src.mode in ("P", "PA") or "transparency" in src.info:
                        src = src.convert("RGBA")
                        flat = Image.new("RGB", src.size, "white")
                        flat.paste(src, mask=src.split()[-1])
                        src = flat
                    else:
                        src = src.convert("RGB")
                    box_w, box_h = W - 2 * pad, H - 2 * pad
                    scale = min(box_w / src.width, box_h / src.height)
                    nw = max(1, int(src.width * scale))
                    nh = max(1, int(src.height * scale))
                    img.paste(src.resize((nw, nh), Image.LANCZOS), ((W - nw) // 2, (H - nh) // 2))
            else:
                # PIL liczy współrzędne od góry; pasek kontynentu ma być na dole karty
                inner_x, inner_y = pad, pad
                inner_w, inner_h = W - 2 * pad, H - 2 * pad
                band_top = H - pad - band_h
                if cont_key:
                    draw.rectangle(
                        [inner_x, band_top, inner_x + inner_w, band_top + band_h],
                        fill=tuple(int(c * 255) for c in cont_color),
                    )
                code_h = int(0.075 * H) if show_code else 0
                name_top = inner_y + code_h
                name_bottom = band_top if cont_key else (H - pad)
                name_h = name_bottom - name_top
                max_w = inner_w
                start_size = min(card_h_mm * 0.30, card_w_mm * 0.13) * px_per_mm

                def pil_measure(text: str, s: float) -> float:
                    return load(font_bold, max(1, int(round(s)))).getlength(text)

                lines, size = fit_text(card.name, pil_measure, max_w, name_h, start_size, min_size=8)
                total = len(lines) * size * LINE_SPACING
                ty = name_top + (name_h - total) / 2.0
                for line in lines:
                    font = load(font_bold, int(size))
                    tw = font.getlength(line)
                    draw.text(((W - tw) / 2, ty), line, font=font, fill=(26, 26, 31))
                    ty += size * LINE_SPACING

                if cont_key:
                    band_size = min(int(0.085 * H), int(band_h * 0.62))
                    font = load(font_bold, band_size)
                    ascent, descent = font.getmetrics()
                    tw = font.getlength(cont_label)
                    draw.text(
                        ((W - tw) / 2, band_top + (band_h - (ascent + descent)) / 2.0),
                        cont_label,
                        font=font,
                        fill=(255, 255, 255),
                    )
                if show_code:
                    font = load(font_regular, int(0.065 * H))
                    draw.text(
                        (inner_x, inner_y),
                        card.code.upper(),
                        font=font,
                        fill=(140, 140, 148),
                    )

            draw.rectangle([0, 0, W - 1, H - 1], outline=(200, 200, 205), width=max(1, dpi // 300))
            img.save(out_dir / f"{card.code}_{side}.png", dpi=(dpi, dpi))


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #


PL_COLLATION = {
    "ą": ("a", 1), "ć": ("c", 1), "ę": ("e", 1), "ł": ("l", 1),
    "ń": ("n", 1), "ó": ("o", 1), "ś": ("s", 1), "ź": ("z", 1), "ż": ("z", 2),
}


def polish_key(text: str) -> list[tuple[str, int]]:
    """Sort key following the Polish alphabet (ą after a, ł after l, ż after ź)."""
    key: list[tuple[str, int]] = []
    for ch in text.lower():
        base, priority = PL_COLLATION.get(ch, (ch, 0))
        key.append((base, priority))
    return key


def parse_size(text: str) -> tuple[float, float]:
    try:
        if "x" in text.lower():
            a, b = text.lower().split("x", 1)
            return float(a), float(b)
        value = float(text)
        return value, value
    except ValueError:
        raise argparse.ArgumentTypeError(f"Niepoprawny rozmiar: {text!r} (np. 60x40)")


def select_codes(args, names: dict[str, str]) -> list[str]:
    if args.only:
        wanted = {c.lower() for c in args.only}
        unknown = [c for c in sorted(wanted) if c not in names]
        if unknown:
            raise SystemExit(f"Nieznane kody krajów: {', '.join(unknown)}")
        codes = list(wanted)
    elif args.set == "sovereign":
        codes = list(SOVEREIGN)
    elif args.set == "countries":
        codes = [
            c
            for c in names
            if c not in ("eu", "un") and not c.startswith("us-") and not c.startswith("gb-")
        ]
    else:
        codes = list(names)

    for extra in args.include:
        extra = extra.lower()
        if extra not in names:
            raise SystemExit(f"Nieznany kod kraju: {extra}")
        if extra not in codes:
            codes.append(extra)

    codes = [c for c in codes if c in names]
    if args.sort == "name":
        codes.sort(key=lambda c: polish_key(names[c]))
    else:
        codes.sort()
    return codes


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generuje dwustronne karty z flagą (przód) i nazwą kraju po polsku (tył).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--papers", nargs="+", default=["A4", "A3"], choices=list(PAPER_SIZES_MM))
    parser.add_argument("--card", type=parse_size, default=(60.0, 40.0), help="Rozmiar karty w mm")
    parser.add_argument("--margin", type=float, default=5.0, help="Minimalny margines arkusza (mm)")
    parser.add_argument("--padding", type=float, default=3.5, help="Odstęp flagi od krawędzi karty (mm)")
    parser.add_argument("--set", choices=["sovereign", "countries", "all"], default="sovereign")
    parser.add_argument("--include", nargs="*", default=[], metavar="CODE", help="Dodatkowe kody, np. xk tw")
    parser.add_argument("--only", nargs="*", default=[], metavar="CODE", help="Tylko wskazane kody")
    parser.add_argument("--sort", choices=["name", "code"], default="name")
    parser.add_argument("--lang", default="pl", help="Język nazw krajów w codes.json")
    parser.add_argument("--duplex", choices=["long", "short", "both", "none"], default="long")
    parser.add_argument("--emit", choices=["pdf", "png", "both"], default="pdf")
    parser.add_argument("--dpi", type=int, default=300, help="Rozdzielcść kart PNG")
    parser.add_argument("--flag-width", type=int, default=640, help="Szerokość pobieranej flagi (px)")
    parser.add_argument("--show-code", action="store_true", help="Drukuj kod ISO na tyle karty")
    parser.add_argument("--no-continent", action="store_true", help="Nie drukuj kontynentu na tyle karty")
    parser.add_argument("--no-borders", action="store_true", help="Nie rysuj linii cięcia")
    parser.add_argument("--out", default="cards_out", help="Katalog wyjściowy")
    parser.add_argument("--cache-dir", default=None, help="Katalog cache flag (domyślnie <out>/.flag-cache)")
    parser.add_argument("--dry-run", action="store_true", help="Tylko pokaż plan, nie generuj plików")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = Path(args.cache_dir) if args.cache_dir else out_dir / ".flag-cache"

    font_regular = find_font(FONT_CANDIDATES_REGULAR)
    font_bold = find_font(FONT_CANDIDATES_BOLD)
    if not (font_regular and font_bold):
        print(
            "⚠ Nie znaleziono fontu TrueType z polskimi znakami – użyty zostanie Helvetica "
            "(polskie znaki mogą być błędne).",
            file=sys.stderr,
        )

    print("Pobieranie listy krajów…", file=sys.stderr)
    names = fetch_json(f"{CDN}/{args.lang}/codes.json")

    codes = select_codes(args, names)
    if not codes:
        raise SystemExit("Brak krajów do wygenerowania.")
    print(f"Kraje: {len(codes)}", file=sys.stderr)

    flag_paths = download_flags(codes, cache_dir, args.flag_width)
    codes = [c for c in codes if c in flag_paths]
    if not codes:
        raise SystemExit("Nie udało się pobrać żadnej flagi.")

    card_w, card_h = args.card
    show_code = args.show_code
    show_continent = not args.no_continent
    draw_borders = not args.no_borders

    for paper in args.papers:
        front_grid = build_grid(paper, card_w, card_h, args.margin, codes, names)
        sheets = max(card.sheet for card in front_grid.cards) + 1
        print(
            f"{paper}: siatka {front_grid.cols}x{front_grid.rows} "
            f"({front_grid.per_sheet} kart/arkusz), {sheets} arkuszy",
            file=sys.stderr,
        )

        if args.dry_run:
            continue

        make_pdf(
            front_grid, "front", flag_paths, out_dir / f"karty_{paper}_przod.pdf",
            args.padding, show_code, show_continent, draw_borders, font_regular, font_bold,
            f"Karty flag {paper} - przód (flagi)",
        )

        variants = []
        if args.duplex == "both":
            variants = [("long", "flip-dlugiej"), ("short", "flip-krotkiej")]
        elif args.duplex == "none":
            variants = [("none", "bez-mirror")]
        else:
            variants = [(args.duplex, "flip-dlugiej" if args.duplex == "long" else "flip-krotkiej")]

        for variant, label in variants:
            back_grid = build_grid(
                paper, card_w, card_h, args.margin, codes, names,
                mirror_long=(variant == "long"),
                mirror_short=(variant == "short"),
            )
            make_pdf(
                back_grid, "back", flag_paths, out_dir / f"karty_{paper}_tyl_{label}.pdf",
                args.padding, show_code, show_continent, draw_borders, font_regular, font_bold,
                f"Karty flag {paper} - tył (nazwy), {label}",
            )
            print(f"  → {out_dir / f'karty_{paper}_przod.pdf'}", file=sys.stderr)
            print(f"  → {out_dir / f'karty_{paper}_tyl_{label}.pdf'}", file=sys.stderr)

        with open(out_dir / f"indeks_{paper}.csv", "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(["arkusz", "wiersz", "kolumna", "kod", "nazwa", "kontynent"])
            for card in sorted(front_grid.cards, key=lambda c_: (c_.sheet, c_.row, c_.col)):
                writer.writerow(
                    [card.sheet + 1, card.row + 1, card.col + 1, card.code, card.name,
                     CONTINENT_STYLE.get(card.continent, ("",))[0]]
                )

    if args.emit in ("png", "both"):
        png_dir = out_dir / "karty_png"
        png_grid = build_grid(args.papers[0], card_w, card_h, args.margin, codes, names)
        make_card_pngs(
            png_grid.cards, flag_paths, png_dir, card_w, card_h, args.dpi,
            args.padding, show_code, show_continent, font_regular, font_bold,
        )
        print(f"  → {png_dir}/", file=sys.stderr)

    if args.dry_run:
        return 0
    print(f"Gotowe. Pliki w: {out_dir.resolve()}")
    return 0


def find_font(candidates: list[str]) -> str | None:
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


if __name__ == "__main__":
    sys.exit(main())
