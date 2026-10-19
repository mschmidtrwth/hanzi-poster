#!/usr/bin/env python3
"""
Build data/unified_hanzi.csv (the input for poster.py) from the lists in data/.

Downloads complete.json from drkameleon/complete-hsk-vocabulary on first run.
Run from anywhere:  python hanzi.py   (add --refresh to re-download complete.json)
"""
import csv
import json
import sys
import urllib.request
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"
COMPLETE_URL = "https://raw.githubusercontent.com/drkameleon/complete-hsk-vocabulary/main/complete.json"


def fetch_complete(refresh=False):
    """Download complete.json into data/ unless it is already there."""
    path = DATA / "complete.json"
    if refresh or not path.exists():
        print(f"downloading {COMPLETE_URL}", file=sys.stderr)
        urllib.request.urlretrieve(COMPLETE_URL, path)
    return path


def mine_hsk_hanzi(refresh=False):
    """
    Mine the lowest HSK level of each Hanzi character from the HSK word list
    and write it to data/hsk_hanzi.txt as "<char> <level>".

    HSK JSON has the following format:
    { "simplified" : "阿拉伯语",
    "radical"    : "阝",
    "level"      : [ "new-7" ],
    "frequency"  : 27202,
    "pos"        : [ "nz" ],
    "forms"      : [ { "traditional"    : "阿拉伯語",
                       "transcriptions" : { "pinyin"    : "Ā lā bó yǔ",
                                            "numeric"   : "A1 la1 bo2 yu3",
                                            "wadegiles" : "a¹ la¹ po² yü³",
                                            "bopomofo"  : "ㄚ ㄌㄚ ㄅㄛˊ ㄩˇ",
                                            "romatzyh"  : "a lha bor yeu" },
                       "meanings"       : [ "Arabic (language)" ],
                       "classifiers"    : [] } ] }

    Only the "newest-X" and "new-X" entries of the level field are used.
    """
    newest, new = {}, {}
    with open(fetch_complete(refresh), "r", encoding="utf-8") as f:
        for entry in json.load(f):
            for level in entry.get("level", []):
                kind, _, n = level.partition("-")
                table = {"newest": newest, "new": new}.get(kind)
                if table is not None:
                    for char in entry.get("simplified", ""):
                        table[char] = min(int(n), table.get(char, 99))
    # Prefer the "newest-X" level and fall back to "new-X"; either way keep the lowest level seen
    hsk_hanzi = {**new, **newest}
    with open(DATA / "hsk_hanzi.txt", "w", encoding="utf-8") as f:
        for char in sorted(hsk_hanzi):
            f.write(f"{char} {hsk_hanzi[char]}\n")


def unify_lists():
    """
    Unify the 3k frequency list, the previously mined HSK list and the individual HSK level lists into a cohesive csv
    """
    # Load the 3k frequency list, single character followed by index, e.g. "的 1"
    with open(DATA / "3k_freq.txt", "r", encoding="utf-8") as f:
        freq_list = f.read().splitlines()

    # Load Jun Da's frequency list, csv with columns: Index,Hanzi,Frequency,Log Frequency,Pinyin,Meaning
    with open(DATA / "junda.csv", "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader)  # Skip header
        junda_list = [row for row in reader]

    # Load the HSK list, character followed by level ("new-X" or "newest-X")
    with open(DATA / "hsk_hanzi.txt", "r", encoding="utf-8") as f:
        hsk_list = f.read().splitlines()

    # Load the individual HSK level lists, format "jǐ 己 self"
    hsk_list2 = []
    for index, filename in enumerate(["hsk1.txt", "hsk2.txt", "hsk3.txt", "hsk4.txt", "hsk5.txt", "hsk6.txt", "hsk7.txt"]):
        with open(DATA / filename, "r", encoding="utf-8") as f:
            # Strip whitespace (some files are indented) and skip empty lines
            level_list = [line.strip() for line in f.read().splitlines() if line.strip()]
            annotated_level_list = [(line, index + 1) for line in level_list]
            hsk_list2.extend(annotated_level_list)

    # Create a unified dictionary with character as key and a list of sources as value
    # Columns: Character, Jun Da, HSK level (unified), HSK level (individual), Pinyin, Meaning
    junda_dict = {}
    for entry in junda_list:
        index, char, frequency, log_frequency, pinyin, meaning = entry
        junda_dict[char] = frequency
    unified_dict = {}
    for entry in hsk_list:
        char, level = entry.split(" ")
        if char in unified_dict:
            unified_dict[char].append(level)
        else:
            unified_dict[char] = [level]
    level_dict = {}
    for entry, index in hsk_list2:
        pinyin, char, meaning = entry.split(" ", 2)
        if char in level_dict:
            # If the character is already in the dictionary, we want to keep the lowest level
            existing_level = level_dict[char][2]
            if index < existing_level:
                level_dict[char] = (pinyin, meaning, index)
        else:
            level_dict[char] = (pinyin, meaning, index)
    # Write the unified dictionary to a CSV file
    with open(DATA / "unified_hanzi.csv", "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Character", "Jun Da", "HSK level (unified)", "HSK level (individual)", "Pinyin", "Meaning"])
        for char in sorted(set(list(junda_dict.keys()) + list(unified_dict.keys()) + list(level_dict.keys()))):
            junda = junda_dict.get(char, "")
            hsk_unified = unified_dict.get(char, [""])[0]
            hsk_individual = level_dict[char][2] if char in level_dict else ""
            pinyin = level_dict[char][0] if char in level_dict else ""
            meaning = level_dict[char][1] if char in level_dict else ""
            writer.writerow([char, junda, hsk_unified, hsk_individual, pinyin, meaning])


if __name__ == "__main__":
    mine_hsk_hanzi(refresh="--refresh" in sys.argv)
    unify_lists()
    print(f"wrote {DATA / 'unified_hanzi.csv'}")
