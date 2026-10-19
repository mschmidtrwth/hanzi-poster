# Hanzi poster

Generate printable posters of Chinese characters (character, pinyin and a short English keyword per block), sorted by HSK level and then by frequency. Output is a vector PDF, SVG or PNG.

## Setup

```sh
pip install -r requirements.txt   # pycairo (may need the cairo dev headers on Linux)
```

The default fonts are Noto Serif/Sans CJK SC. Install them or pick others with `--char-font` / `--text-font`.

`data/unified_hanzi.csv` is included, so you can make posters straight away.

## Sample posters

```sh
# Everything on one A1 sheet (the default)
python poster.py

# A level 1 poster, landscape A4, coloured text
python poster.py --landscape --color-mode text --paper A4 -o level1.pdf --level 1 --level-source individual

# A level 3 poster, portrait A4
python poster.py --paper A4 -o level3.pdf --level 3 --level-source individual

# All levels on A0 with a title and a colour legend, each level starting on a new row
python poster.py --paper A0 --break-levels --legend --title "汉字 · HSK" -o all.pdf

# Level 4 with a fixed block size (25 mm wide), spilling onto extra A4 pages as needed
python poster.py --paper A4 --block-mm 25 --level 4 --level-source individual -o level4.pdf

# Level 2 with custom colours, PNG output
python poster.py --paper A4 --level 2 --level-source individual --colors "1=#d62828,2=#f77f00" --color-mode both -o preview.png
```

Run `python poster.py --help` for all options (paper size, margins, grid, fonts, colours, ...).

`--level-source` decides which HSK level a character gets: `individual` (the per-level word lists in `data/hsk1.txt` ... `hsk7.txt`), `unified` (levels mined from complete-hsk-vocabulary), or `min` (the lower of the two, the default).

## Rebuilding the data

```sh
python hanzi.py             # downloads data/complete.json on first run
python hanzi.py --refresh   # re-download it
```

This downloads `complete.json` from [drkameleon/complete-hsk-vocabulary](https://github.com/drkameleon/complete-hsk-vocabulary), mines the lowest HSK level per character, and merges it with the other lists in `data/` into `data/unified_hanzi.csv`.

| File | Contents |
| --- | --- |
| `data/hsk1.txt` ... `hsk7.txt` | per-level lists (`pinyin 字 meaning`) |
| `data/junda.csv` | character frequencies (Jun Da) |
| `data/3k_freq.txt` | 3000-character frequency list |
| `data/complete.json` | downloaded, not committed |
| `data/unified_hanzi.csv` | generated; the input to `poster.py` |
