# Karty z flagami / Flag cards

**This is a work of AI.** The repository, its code, generated data and commit history were created by an AI assistant (opencode). Human involvement was limited to giving requests, reviewing results and printing the cards.

A Python tool for generating printable, two-sided country flag cards. The front of each card shows the national flag; the back shows the country name in Polish, its capital, continent, language/currency facts and a locator map with neighbouring countries highlighted. Cards are arranged in grids on A4/A3 sheets, so they can be printed duplex and cut out.

## What is in the repository

- `make_flag_cards.py` — main generator (PDF and/or PNG output, A4/A3/A5/Letter, configurable card size, duplex modes, map and text options).
- `fetch_facts.py`, `fetch_facts2.py`, `fetch_quick.py` — helper scripts used to gather supplementary country facts.
- `facts_lang_cur.json`, `geo_facts.json`, `ne_50m_admin_0_countries.geojson` — bundled data for facts, capitals and locator maps.
- `make_both_sizes.sh` — convenience script that regenerates the two committed output sets. Note: it assumes the checkout lives in `/root/flag_cards`.
- `out_79x47/`, `out_80x53/` — example outputs: front sheets (`karty_A4_przod.pdf`), back sheets for long- and short-edge duplex (`karty_A4_tyl_flip-*.pdf`), a CSV index and individual card PNGs.
- `.flag-cache/` — cached flag images.

## Requirements

- Python 3
- `reportlab` and `pillow` (`python3 -m pip install reportlab pillow`)
- System fonts such as DejaVu Sans, Liberation Sans or Noto Sans
- Internet access on first run to download flags from flagcdn.com (downloaded flags are cached locally)

## Usage

```bash
python3 -m pip install reportlab pillow
python3 make_flag_cards.py --papers A4 --duplex both --emit both \
    --card 80x53 --margin 5 --cache-dir .flag-cache --out out_80x53
```

Run `python3 make_flag_cards.py --help` for all options, including `--only`, `--include`, `--set`, `--no-map`, `--no-facts` and `--dry-run`.

## License

MIT — see [LICENSE](LICENSE).
