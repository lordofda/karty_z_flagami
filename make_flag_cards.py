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
import math
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:  # PNG output / maps need Pillow, PDF does not
    Image = ImageDraw = ImageFont = None  # type: ignore[assignment]

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

CDN = "https://flagcdn.com"
MAP_GEO_URL = (
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/"
    "geojson/ne_50m_admin_0_countries.geojson"
)
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

# Stolica (po polsku) - źródło: flagi-panstw.pl (strony krajów)
CAPITALS_BY_CODE = {
    "ad": "Andora", "ae": "Abu Zabi", "af": "Kabul", "ag": "St. John’s", "ai": "The Valley", "al": "Tirana",
    "am": "Erywań", "ao": "Luanda", "ar": "Buenos Aires", "as": "Pago Pago", "at": "Wiedeń", "au": "Canberra",
    "aw": "Oranjestad", "ax": "Maarianhamina", "az": "Baku", "ba": "Sarajewo", "bb": "Bridgetown",
    "bd": "Dhaka", "be": "Bruksela", "bf": "Wagadugu", "bg": "Sofia", "bh": "Manama", "bi": "Gitega",
    "bj": "Porto-Novo", "bl": "Gustavia", "bm": "Hamilton", "bn": "Bandar Seri Begawan", "bo": "Sucre",
    "br": "Brasília", "bs": "Nassau", "bt": "Thimphu", "bw": "Gaborone", "by": "Mińsk", "bz": "Belmopan",
    "ca": "Ottawa", "cc": "Wyspa Zachodnia", "cd": "Kinszasa", "cf": "Bangi", "cg": "Brazzaville",
    "ch": "Berno", "ci": "Jamusukro", "ck": "Avarua", "cl": "Santiago", "cm": "Jaunde", "cn": "Pekin",
    "co": "Bogota", "cr": "San Jose", "cu": "Hawana", "cv": "Praia", "cw": "Willemstad",
    "cx": "Flying Fish Cove", "cy": "Nikozja", "cz": "Praga", "de": "Berlin", "dj": "Dżibuti",
    "dk": "Kopenhaga", "dm": "Roseau", "do": "Santo Domingo", "dz": "Algier", "ec": "Quito", "ee": "Tallinn",
    "eg": "Kair", "eh": "Al-Ujun", "er": "Asmara", "es": "Madryt", "et": "Addis Abeba", "fi": "Helsinki",
    "fj": "Suva", "fk": "Stanley", "fm": "Palikir", "fo": "Thorshavn", "fr": "Paryż", "ga": "Libreville",
    "gb": "Londyn", "gd": "Saint George", "ge": "Tbilisi", "gf": "Kajenna", "gg": "Saint Peter Port",
    "gh": "Akra", "gi": "Gibraltar", "gl": "Nuuk", "gm": "Bandżul", "gn": "Konakry", "gp": "Basse-Terre",
    "gq": "Malabo", "gr": "Ateny", "gt": "Gwatemala", "gu": "Hagåtña", "gw": "Bissau", "gy": "Georgetown",
    "hk": "Victoria", "hn": "Tegucigalpa", "hr": "Zagrzeb", "ht": "Port-au-Prince", "hu": "Budapeszt",
    "id": "Dżakarta", "ie": "Dublin", "il": "Jerozolima", "im": "Douglas", "in": "Nowe Delhi",
    "io": "Diego Garcia", "iq": "Bagdad", "ir": "Teheran", "is": "Reykjavík", "it": "Rzym",
    "je": "Saint Helier", "jm": "Kingston", "jo": "Amman", "jp": "Tokio", "ke": "Nairobi", "kg": "Biszkek",
    "kh": "Phnom Penh", "ki": "South Tarawa", "km": "Moroni", "kn": "Basseterre", "kp": "Pjongjang",
    "kr": "Seul", "kw": "Kuwejt", "ky": "Georgetown", "kz": "Astana", "la": "Wientian", "lb": "Bejrut",
    "lc": "Castries", "li": "Vaduz", "lk": "Kolombo", "lr": "Monrovia", "ls": "Maseru", "lt": "Wilno",
    "lu": "Luksemburg", "lv": "Ryga", "ly": "Trypolis", "ma": "Rabat", "mc": "Monako", "md": "Kiszyniów",
    "me": "Podgorica", "mf": "Marigot", "mg": "Antananarywa", "mh": "Majuro", "mk": "Skopje", "ml": "Bamako",
    "mm": "Naypyidaw", "mn": "Ułan Bator", "mp": "Saipan", "mq": "Fort-de-France", "mr": "Nawakszut",
    "ms": "Plymouth", "mt": "Valletta", "mu": "Port Louis", "mv": "Male", "mw": "Lilongwe", "mx": "Meksyk",
    "my": "Kuala Lumpur", "mz": "Maputo", "na": "Windhuk", "nc": "Numea", "ne": "Niamey", "nf": "Kingston",
    "ng": "Abudża", "ni": "Managua", "nl": "Amsterdam", "no": "Oslo", "np": "Katmandu", "nr": "Yaren",
    "nu": "Alofi", "nz": "Wellington", "om": "Maskat", "pa": "Panama", "pe": "Lima", "pf": "Papeete",
    "pg": "Port Moresby", "ph": "Manila", "pk": "Islamabad", "pl": "Warszawa", "pm": "Saint-Pierre",
    "pn": "Adamstown", "pr": "San Juan", "ps": "Ramallah", "pt": "Lizbona", "pw": "Ngerulmud",
    "py": "Asunción", "qa": "Doha", "re": "Saint-Denis", "ro": "Bukareszt", "rs": "Belgrad", "ru": "Moskwa",
    "rw": "Kigali", "sa": "Rijad", "sb": "Honiara", "sc": "Victoria", "sd": "Chartum", "se": "Sztokholm",
    "sg": "Singapur", "sh": "Jamestown", "si": "Lublana", "sj": "Longyearbyen", "sk": "Bratysława",
    "sl": "Freetown", "sm": "San Marino", "sn": "Dakar", "so": "Mogadiszu", "sr": "Paramaribo", "ss": "Dżuba",
    "st": "São Tomé", "sv": "San Salvador", "sx": "Philipsburg", "sy": "Damaszek", "sz": "Lobamba",
    "tc": "Cockburn Town", "td": "Ndżamena", "tg": "Lomé", "th": "Bangkok", "tj": "Duszanbe", "tk": "Fakaofo",
    "tl": "Dili", "tm": "Aszchabad", "tn": "Tunis", "to": "Nukuʻalofa", "tr": "Ankara", "tt": "Port-of-Spain",
    "tv": "Funafuti", "tw": "Tajpej", "tz": "Dodoma", "ua": "Kijów", "ug": "Kampala", "us": "Waszyngton",
    "uy": "Montevideo", "uz": "Taszkent", "va": "Watykan", "vc": "Kingstown", "ve": "Caracas",
    "vg": "Road Town", "vi": "Charlotte Amalie", "vn": "Hanoi", "vu": "Port Vila", "wf": "Mata Utu",
    "ws": "Apia", "xk": "Prisztina", "ye": "Sana", "yt": "Mamoudzou",
    "za": "Pretoria, Bloemfontein, Kapsztad", "zm": "Lusaka", "zw": "Harare",
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
# Card back: shared layout + map rendering
# --------------------------------------------------------------------------- #

MAP_GEODATA = "ne_50m_admin_0_countries.geojson"
MAP_CACHE_PX = 512
BACK_BAND_MM = 5.2
BACK_TOP_MM = 5.8
BACK_GAP_MM = 2.0
ARROW_MM = 3.2
PT_TO_MM = 25.4 / 72.0
INK = (0.10, 0.10, 0.12)
MUTED = (0.34, 0.34, 0.38)
LABEL = (0.62, 0.62, 0.65)
SEA_RGB = (232, 241, 249)
NEIGHBOUR_RGB = (217, 222, 228)
MAP_BORDER_RGB = (255, 255, 255)

_MAP_POLYS = {}


def _merc_y(lat: float) -> float:
    lat = max(-85.0, min(85.0, lat))
    return math.degrees(math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)))


def _ring_bbox(ring):
    xs = [p[0] for p in ring]
    ys = [p[1] for p in ring]
    return (min(xs), min(ys), max(xs), max(ys))


def _download(url: str, dest: Path, timeout: int = 120) -> None:
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "make_flag_cards.py"})
    with urllib.request.urlopen(req, timeout=timeout) as resp, open(tmp, "wb") as fh:
        while True:
            chunk = resp.read(1 << 16)
            if not chunk:
                break
            fh.write(chunk)
    tmp.replace(dest)


def _load_map_polys(geojson_path: Path) -> dict[str, list]:
    key = str(geojson_path)
    if key in _MAP_POLYS:
        return _MAP_POLYS[key]
    polys_by: dict[str, list] = {}
    try:
        gj = json.loads(Path(geojson_path).read_text(encoding="utf-8"))
    except Exception:
        _MAP_POLYS[key] = polys_by
        return polys_by
    for f in gj.get("features", []):
        props = f.get("properties", {})
        code = ""
        for prop in ("ISO_A2", "ISO_A2_EH"):
            val = (props.get(prop) or "").strip().lower()
            if val and val != "-99":
                code = val
                break
        geom = f.get("geometry")
        if not code or not geom:
            continue
        if geom.get("type") == "Polygon":
            polys = [geom["coordinates"]]
        elif geom.get("type") == "MultiPolygon":
            polys = geom["coordinates"]
        else:
            continue
        polys_by.setdefault(code, []).extend(polys)
    _MAP_POLYS[key] = polys_by
    return polys_by


def render_locator_map(code: str, fill_rgb, geojson_path: Path, px: int = 512):
    """Small locator map: country in `fill_rgb`, neighbours in light grey."""
    if Image is None:
        return None
    polys_by = _load_map_polys(geojson_path)
    polys = polys_by.get(code)
    if not polys:
        return None
    fill = tuple(int(round(c * 255)) for c in fill_rgb)

    bbs = [_ring_bbox(p[0]) for p in polys]
    main = max(range(len(polys)), key=lambda i: max(1e-9, (bbs[i][2] - bbs[i][0]) * (bbs[i][3] - bbs[i][1])))
    mb = bbs[main]
    mba = max(1e-9, (mb[2] - mb[0]) * (mb[3] - mb[1]))
    cx_main = (mb[0] + mb[2]) / 2.0

    kept = []
    for i, poly in enumerate(polys):
        bb = bbs[i]
        shift = 360.0 * round((cx_main - (bb[0] + bb[2]) / 2.0) / 360.0)
        dx = max(0.0, mb[0] - (bb[2] + shift), (bb[0] + shift) - mb[2])
        dy = max(0.0, mb[1] - bb[3], bb[1] - mb[3])
        if i == main or ((bb[2] - bb[0]) * (bb[3] - bb[1]) >= 0.01 * mba and dx <= 15 and dy <= 10):
            kept.append((poly, shift))

    xs, ys = [], []
    for poly, shift in kept:
        for ring in poly:
            for lon, lat in ring:
                xs.append(lon + shift)
                ys.append(lat)
    if not xs:
        return None
    lon0, lon1 = min(xs), max(xs)
    lat0, lat1 = max(-84.0, min(ys)), min(84.0, max(ys))
    latc = (lat0 + lat1) / 2.0
    y0, y1 = _merc_y(lat0), _merc_y(lat1)
    min_y = _merc_y(latc + 1.5) - _merc_y(latc - 1.5)
    span = max(lon1 - lon0, 3.0, y1 - y0, min_y) * 1.12
    cx = (lon0 + lon1) / 2.0
    cy = (y0 + y1) / 2.0
    vx0, vy1 = cx - span / 2.0, cy + span / 2.0

    def P(lon, lat):
        return ((lon - vx0) / span * px, (vy1 - _merc_y(lat)) / span * px)

    img = Image.new("RGB", (px, px), SEA_RGB)
    draw = ImageDraw.Draw(img)

    def paint(poly, shift, fill_col, width):
        pts = [P(lon + shift, lat) for lon, lat in poly[0]]
        if len(pts) >= 3:
            draw.polygon(pts, fill=fill_col)
            if width:
                draw.line(pts + [pts[0]], fill=MAP_BORDER_RGB, width=width)

    border_w = max(1, px // 320)
    for other, other_polys in polys_by.items():
        if other == code:
            continue
        for poly in other_polys:
            bb = _ring_bbox(poly[0])
            shift = 360.0 * round((cx - (bb[0] + bb[2]) / 2.0) / 360.0)
            if bb[2] + shift < vx0 - span or bb[0] + shift > vx0 + 2 * span:
                continue
            if _merc_y(bb[3]) < vy1 - span or _merc_y(bb[1]) > vy1 + span:
                continue
            paint(poly, shift, NEIGHBOUR_RGB, border_w)

    target_pts = []
    for poly, shift in kept:
        for ring in poly:
            for lon, lat in ring:
                target_pts.append(P(lon + shift, lat))
    if not target_pts:
        return None

    mask = Image.new("L", (px, px), 0)
    mdraw = ImageDraw.Draw(mask)
    for poly, shift in kept:
        outer = [P(lon + shift, lat) for lon, lat in poly[0]]
        if len(outer) >= 3:
            mdraw.polygon(outer, fill=255)
        for hole in poly[1:]:
            hole_pts = [P(lon + shift, lat) for lon, lat in hole]
            if len(hole_pts) >= 3:
                mdraw.polygon(hole_pts, fill=0)
    img.paste(fill, (0, 0), mask)

    land_px = mask.histogram()[255]
    if land_px < 0.004 * px * px:
        # tiny/microstate or scattered atolls: draw locator dots
        order = sorted(range(len(kept)),
                       key=lambda i: (lambda bb: (bb[2] - bb[0]) * (bb[3] - bb[1]))(_ring_bbox(kept[i][0][0])),
                       reverse=True)
        r_out = max(5.0, 0.042 * px)
        r_in = max(3.0, 0.030 * px)
        for i in order[:12]:
            poly, shift = kept[i]
            pts = [P(lon + shift, lat) for lon, lat in poly[0]]
            ccx = (min(p[0] for p in pts) + max(p[0] for p in pts)) / 2.0
            ccy = (min(p[1] for p in pts) + max(p[1] for p in pts)) / 2.0
            draw.ellipse([ccx - r_out, ccy - r_out, ccx + r_out, ccy + r_out], fill=(255, 255, 255))
            draw.ellipse([ccx - r_in, ccy - r_in, ccx + r_in, ccy + r_in], fill=fill)
    else:
        for poly, shift in kept:
            pts = [P(lon + shift, lat) for lon, lat in poly[0]]
            if len(pts) >= 3:
                draw.line(pts + [pts[0]], fill=MAP_BORDER_RGB, width=border_w)
    return img


def ensure_map_png(code: str, fill_rgb, map_dir: Path | None, geojson_path: Path,
                   refresh: bool = False) -> Path | None:
    if map_dir is None:
        return None
    hexc = "".join("%02x" % int(round(c * 255)) for c in fill_rgb)
    path = map_dir / ("%s-%s-v3.png" % (code, hexc))
    if path.exists() and not refresh:
        return path
    img = render_locator_map(code, fill_rgb, geojson_path, MAP_CACHE_PX)
    if img is None:
        return None
    map_dir.mkdir(parents=True, exist_ok=True)
    img.save(path)
    return path


def back_geometry(card_w: float, card_h: float, padding: float,
                  has_map: bool, has_band: bool, has_top: bool):
    ix, iy = padding, padding
    iw, ih = card_w - 2.0 * padding, card_h - 2.0 * padding
    band_h = max(3.4, min(BACK_BAND_MM, ih * 0.17)) if has_band else 0.0
    top_h = min(BACK_TOP_MM, ih * 0.19) if has_top else 0.0
    content_h = ih - top_h - band_h
    map_size = 0.0
    if has_map:
        avail = content_h
        map_size = max(0.0, min(avail, iw * 0.42))
        if map_size < 7.0:
            map_size = 0.0
    text_x = ix + (map_size + BACK_GAP_MM if map_size else 0.0)
    text_h = map_size if map_size else content_h
    return {
        "ix": ix, "iy": iy, "iw": iw, "ih": ih,
        "band_h": band_h, "top_h": top_h,
        "map": (ix, iy + top_h, map_size, map_size),
        "text": (text_x, iy + top_h, ix + iw - text_x, text_h),
        "band_y": iy + ih - band_h,
    }


def back_content(card, card_w, card_h, padding, measure, show_code, show_continent,
                 map_path, show_arrow=True, show_capital=True):
    """Return drawing primitives in card-local mm (y measured from the top)."""
    mm_to_pt = 72.0 / 25.4
    cont_key = card.continent if show_continent else None
    cont_label, cont_color = (
        CONTINENT_STYLE.get(cont_key, ("", (0.5, 0.5, 0.5))) if cont_key else ("", (0.5, 0.5, 0.5))
    )
    g = back_geometry(card_w, card_h, padding,
                      has_map=map_path is not None,
                      has_band=bool(cont_key),
                      has_top=show_arrow or show_code)
    items: list[tuple] = []

    if cont_key:
        items.append(("rect", g["ix"], g["band_y"], g["iw"], g["band_h"], cont_color))

    if show_arrow or show_code:
        top_y, top_h = g["iy"], g["top_h"]
        if show_arrow:
            ax = g["ix"]
            ay = top_y + (top_h - ARROW_MM) / 2.0
            items.append(("arrow", ax, ay, ARROW_MM, ARROW_MM, (0.36, 0.36, 0.40)))
            size = min(4.6, max(3.2, ARROW_MM * 1.3))
            items.append(("text", "góra flagi", ax + ARROW_MM + 0.9,
                          top_y + top_h / 2.0 + size * PT_TO_MM * 0.34,
                          size, LABEL, False, "left"))
        if show_code:
            size = min(6.5, max(4.0, card_h * 0.115))
            items.append(("text", card.code.upper(), g["ix"] + g["iw"],
                          top_y + top_h / 2.0 + size * PT_TO_MM * 0.34,
                          size, LABEL, True, "right"))

    if map_path is not None:
        mx, my, mw, mh = g["map"]
        items.append(("image", map_path, mx, my, mw, mh))

    tx, ty, tw, th = g["text"]
    cap_text = ("Stolica: " + CAPITALS_BY_CODE[card.code]) if (show_capital and card.code in CAPITALS_BY_CODE) else None
    cap_lines: list[str] = []
    cap_size = 0.0
    if cap_text:
        cap_start = min(5.8, max(3.8, card_h * 0.145))
        cap_lines, cap_size = fit_text(cap_text, measure, tw * mm_to_pt,
                                       2.3 * cap_start * LINE_SPACING, cap_start,
                                       min_size=3.2)
    gap = 1.3 if cap_lines else 0.0
    cap_h = len(cap_lines) * cap_size * LINE_SPACING * PT_TO_MM
    name_max_h = max(3.5, th - cap_h - gap)
    name_start = min(card_h * 0.30, 16.0)
    name_lines, name_size = fit_text(card.name, measure, tw * mm_to_pt,
                                     name_max_h * mm_to_pt, name_start, min_size=3.8)

    total = len(name_lines) * name_size * LINE_SPACING * PT_TO_MM + gap + cap_h
    y = ty + max(0.0, (th - total) / 2.0)
    for line in name_lines:
        items.append(("text", line, tx + tw / 2.0, y + name_size * PT_TO_MM * 0.95,
                      name_size, INK, True, "center"))
        y += name_size * LINE_SPACING * PT_TO_MM
    y += gap
    for line in cap_lines:
        items.append(("text", line, tx + tw / 2.0, y + cap_size * PT_TO_MM * 0.95,
                      cap_size, MUTED, False, "center"))
        y += cap_size * LINE_SPACING * PT_TO_MM

    if cont_key:
        size = min(7.0, max(3.6, g["band_h"] * 1.45))
        items.append(("text", cont_label, g["ix"] + g["iw"] / 2.0,
                      g["band_y"] + g["band_h"] / 2.0 + size * PT_TO_MM * 0.34,
                      size, (1.0, 1.0, 1.0), True, "center"))
    return items


def arrow_polygon(x: float, y: float, w: float, h: float):
    """Up arrow inside the box (x, y, w, h), y measured from the top."""
    return [
        (x + 0.34 * w, y + h),
        (x + 0.34 * w, y + 0.45 * h),
        (x, y + 0.45 * h),
        (x + 0.5 * w, y),
        (x + w, y + 0.45 * h),
        (x + 0.66 * w, y + 0.45 * h),
        (x + 0.66 * w, y + h),
    ]


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
# Drawing primitives (shared by PDF and PNG output)
# --------------------------------------------------------------------------- #


def _cont_color(card, show_continent: bool = True):
    return CONTINENT_STYLE.get(card.continent, ("", (0.5, 0.5, 0.5)))[1]


def _draw_item_pdf(c, item, x_pt, y_pt, card_h_mm, font_name, bold_name):
    from reportlab.lib.utils import ImageReader

    kind = item[0]
    if kind == "rect":
        _, x, y, w, h, rgb = item
        c.setFillColorRGB(*rgb)
        c.rect(x_pt + x * MM, y_pt + (card_h_mm - y - h) * MM, w * MM, h * MM, stroke=0, fill=1)
    elif kind == "text":
        _, text, x, y, size, rgb, bold, anchor = item
        c.setFillColorRGB(*rgb)
        c.setFont(bold_name if bold else font_name, size)
        px = x_pt + x * MM
        py = y_pt + (card_h_mm - y) * MM
        if anchor == "center":
            c.drawCentredString(px, py, text)
        elif anchor == "right":
            c.drawRightString(px, py, text)
        else:
            c.drawString(px, py, text)
    elif kind == "image":
        _, path, x, y, w, h = item
        c.drawImage(ImageReader(str(path)), x_pt + x * MM, y_pt + (card_h_mm - y - h) * MM,
                    width=w * MM, height=h * MM, mask="auto")
    elif kind == "arrow":
        _, x, y, w, h, rgb = item
        c.setFillColorRGB(*rgb)
        pts = arrow_polygon(x, y, w, h)
        p = c.beginPath()
        p.moveTo(x_pt + pts[0][0] * MM, y_pt + (card_h_mm - pts[0][1]) * MM)
        for px, py in pts[1:]:
            p.lineTo(x_pt + px * MM, y_pt + (card_h_mm - py) * MM)
        p.close()
        c.drawPath(p, stroke=0, fill=1)


def _draw_item_png(img, draw, item, px_per_mm, dpi, font_regular, font_bold):
    kind = item[0]
    if kind == "rect":
        _, x, y, w, h, rgb = item
        draw.rectangle([x * px_per_mm, y * px_per_mm, (x + w) * px_per_mm, (y + h) * px_per_mm],
                       fill=tuple(int(round(v * 255)) for v in rgb))
    elif kind == "text":
        _, text, x, y, size, rgb, bold, anchor = item
        font_path = font_bold if bold else font_regular
        if font_path:
            font = ImageFont.truetype(font_path, max(1, int(round(size * dpi / 72.0))))
        else:
            font = ImageFont.load_default()
        ascent = font.getmetrics()[0]
        xpx = x * px_per_mm
        ypx = y * px_per_mm - ascent
        width = font.getlength(text)
        if anchor == "center":
            xpx -= width / 2.0
        elif anchor == "right":
            xpx -= width
        draw.text((xpx, ypx), text, font=font, fill=tuple(int(round(v * 255)) for v in rgb))
    elif kind == "image":
        _, path, x, y, w, h = item
        tw = max(1, int(round(w * px_per_mm)))
        th = max(1, int(round(h * px_per_mm)))
        with Image.open(path) as src:
            img.paste(src.convert("RGB").resize((tw, th), Image.LANCZOS),
                      (int(round(x * px_per_mm)), int(round(y * px_per_mm))))
    elif kind == "arrow":
        _, x, y, w, h, rgb = item
        pts = [(px * px_per_mm, py * px_per_mm) for px, py in arrow_polygon(x, y, w, h)]
        draw.polygon(pts, fill=tuple(int(round(v * 255)) for v in rgb))


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
    map_dir: Path | None = None,
    geojson_path: Path | None = None,
    refresh_maps: bool = False,
    show_arrow: bool = True,
    show_capital: bool = True,
) -> int:
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas as pdfcanvas

    if geojson_path is None:
        geojson_path = Path(__file__).parent / MAP_GEODATA

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
                map_path = ensure_map_png(card.code, _cont_color(card, show_continent),
                                          map_dir, geojson_path, refresh_maps) if map_dir else None
                items = back_content(card, grid.card_w, grid.card_h, padding, measure,
                                     show_code, show_continent, map_path,
                                     show_arrow=show_arrow, show_capital=show_capital)
                for item in items:
                    _draw_item_pdf(c, item, x_pt, y_pt, grid.card_h, font_name, bold_name)
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
    map_dir: Path | None = None,
    geojson_path: Path | None = None,
    refresh_maps: bool = False,
    show_arrow: bool = True,
    show_capital: bool = True,
) -> None:
    if Image is None:
        raise SystemExit("Pillow jest wymagany do --emit png. Zainstaluj: pip install pillow")
    if geojson_path is None:
        geojson_path = Path(__file__).parent / MAP_GEODATA

    px_per_mm = dpi / 25.4
    W = int(round(card_w_mm * px_per_mm))
    H = int(round(card_h_mm * px_per_mm))
    pad = int(round(padding * px_per_mm))
    out_dir.mkdir(parents=True, exist_ok=True)

    def load(path: str | None, size: int):
        if path:
            return ImageFont.truetype(path, max(1, int(round(size))))
        return ImageFont.load_default()

    def measure(text: str, size: float) -> float:
        return load(font_bold, size * dpi / 72.0).getlength(text) * 72.0 / dpi

    for card in cards:
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
                map_path = ensure_map_png(card.code, _cont_color(card, show_continent),
                                          map_dir, geojson_path, refresh_maps) if map_dir else None
                items = back_content(card, card_w_mm, card_h_mm, padding, measure,
                                     show_code, show_continent, map_path,
                                     show_arrow=show_arrow, show_capital=show_capital)
                for item in items:
                    _draw_item_png(img, draw, item, px_per_mm, dpi, font_regular, font_bold)

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
    parser.add_argument("--no-map", action="store_true", help="Nie drukuj mapki lokalizacyjnej na tyle karty")
    parser.add_argument("--no-capital", action="store_true", help="Nie drukuj stolicy na tyle karty")
    parser.add_argument("--no-arrow", action="store_true", help="Nie rysuj strzałki orientacji flagi")
    parser.add_argument("--map-geo", default=None, help="Ścieżka do GeoJSON Natural Earth (domyślnie w katalogu skryptu)")
    parser.add_argument("--refresh-maps", action="store_true", help="Przelicz mapki od nowa (ignoruj cache)")
    parser.add_argument("--no-continent", action="store_true", help="Nie drukuj kontynentu na tyle karty")
    parser.add_argument("--no-borders", action="store_true", help="Nie rysuj linii cięcia")
    parser.add_argument("--out", default="cards_out", help="Katalog wyjściowy")
    parser.add_argument("--cache-dir", default=None, help="Katalog cache flag (domyślnie <out>/.flag-cache)")
    parser.add_argument("--dry-run", action="store_true", help="Tylko pokaż plan, nie generuj plików")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = Path(args.cache_dir) if args.cache_dir else out_dir / ".flag-cache"
    geojson_path = Path(args.map_geo) if args.map_geo else Path(__file__).parent / MAP_GEODATA
    map_dir = None if args.no_map else cache_dir / "maps"
    show_arrow = not args.no_arrow
    show_capital = not args.no_capital

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

    if map_dir is not None and not geojson_path.exists():
        print("Pobieranie danych map (Natural Earth)…", file=sys.stderr)
        try:
            geojson_path.parent.mkdir(parents=True, exist_ok=True)
            _download(MAP_GEO_URL, geojson_path)
        except Exception as exc:
            print(f"  ⚠ nie udało się pobrać map: {exc} – pomijam mapki", file=sys.stderr)
            map_dir = None

    if map_dir is not None and not args.dry_run:
        missing = 0
        for code in codes:
            color = CONTINENT_STYLE.get(CONTINENT_BY_CODE.get(code, "inne"), ("", (0.5, 0.5, 0.5)))[1]
            if ensure_map_png(code, color, map_dir, geojson_path, args.refresh_maps) is None:
                missing += 1
        done = len(codes) - missing
        print(f"Mapy: {done}/{len(codes)}" + (f" (brak dla {missing})" if missing else ""), file=sys.stderr)

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
            map_dir=map_dir, geojson_path=geojson_path, refresh_maps=args.refresh_maps,
            show_arrow=show_arrow, show_capital=show_capital,
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
                map_dir=map_dir, geojson_path=geojson_path, refresh_maps=args.refresh_maps,
                show_arrow=show_arrow, show_capital=show_capital,
            )
            print(f"  → {out_dir / f'karty_{paper}_przod.pdf'}", file=sys.stderr)
            print(f"  → {out_dir / f'karty_{paper}_tyl_{label}.pdf'}", file=sys.stderr)

        with open(out_dir / f"indeks_{paper}.csv", "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(["arkusz", "wiersz", "kolumna", "kod", "nazwa", "stolica", "kontynent"])
            for card in sorted(front_grid.cards, key=lambda c_: (c_.sheet, c_.row, c_.col)):
                writer.writerow(
                    [card.sheet + 1, card.row + 1, card.col + 1, card.code, card.name,
                     CAPITALS_BY_CODE.get(card.code, ""), CONTINENT_STYLE.get(card.continent, ("",))[0]]
                )

    if args.emit in ("png", "both"):
        png_dir = out_dir / "karty_png"
        png_grid = build_grid(args.papers[0], card_w, card_h, args.margin, codes, names)
        make_card_pngs(
            png_grid.cards, flag_paths, png_dir, card_w, card_h, args.dpi,
            args.padding, show_code, show_continent, font_regular, font_bold,
            map_dir=map_dir, geojson_path=geojson_path, refresh_maps=args.refresh_maps,
            show_arrow=show_arrow, show_capital=show_capital,
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
