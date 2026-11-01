#!/bin/bash
set -e
cd /root/flag_cards
python3 -c "import py_compile; py_compile.compile('make_flag_cards.py', doraise=True)"
for size in "79x47" "80x53"; do
    IFS='x' read -r cw ch <<< "$size"
    out="out_${size}"
    rm -rf "$out"
    echo "=== Generating ${size} (${cw}x${ch}) -> ${out} ==="
    python3 make_flag_cards.py \
        --papers A4 \
        --duplex both \
        --emit both \
        --cache-dir .flag-cache \
        --out "$out" \
        --card ${size} \
        --margin 5
    echo "=== Done ${size}: $(ls $out/*.pdf 2>/dev/null | wc -l) PDFs, $(ls $out/karty_png 2>/dev/null | wc -l) PNGs ==="
    echo
done
echo "All done. Outputs in out_79x47/ and out_80x53/"
