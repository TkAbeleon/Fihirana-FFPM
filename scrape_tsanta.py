#!/usr/bin/env python3
"""
Scrape les chants TSANTA depuis Fihirana.org et génère 04_tsanta.json.

Structure compatible avec les fichiers JSON existants du dépôt:
{
  "tsanta_1": {
    "laharana": "1",
    "sokajy": "tsanta",
    "lohateny": "...",
    "mpanoratra": ["..."],
    "hira": [
      {
        "andininy": 1,
        "tononkira": "...",
        "fiverenany": false
      }
    ]
  }
}

Dépendances:
    pip install requests beautifulsoup4

Usage:
    python scrape_tsanta.py
    python scrape_tsanta.py --output 04_tsanta.json
"""

from __future__ import annotations

import argparse
import json
import re
import time
from collections import OrderedDict
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag


BASE_URL = "https://fihirana.org/category/ffpm/tsanta/"
DEFAULT_OUTPUT = "04_tsanta.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; Fihirana-FFPM-TSANTA-scraper/1.0; "
        "+https://github.com/TkAbeleon/Fihirana-FFPM)"
    )
}

SONG_RE = re.compile(r"^TS\\s*(\\d+)\\s*[–—-]\\s*(.+)$", re.IGNORECASE)
VERSE_RE = re.compile(r"^(\\d+)\\.\\s*(.*)$")
CHORUS_RE = re.compile(r"^Fiv\\s*:?\\s*(.*)$", re.IGNORECASE)


def clean_text(text: str) -> str:
    text = text.replace("\\xa0", " ")
    text = re.sub(r"[ \\t]+", " ", text)
    text = re.sub(r"\\n[ \\t]+", "\\n", text)
    return text.strip()


def normalize_block(text: str) -> str:
    lines = []
    for raw in text.splitlines():
        line = clean_text(raw)
        if line:
            lines.append(line)
    return "\\n".join(lines)


def get_soup(session: requests.Session, url: str) -> BeautifulSoup:
    response = session.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding
    return BeautifulSoup(response.text, "html.parser")


def extract_song(article_heading: Tag) -> dict | None:
    match = SONG_RE.match(clean_text(article_heading.get_text(" ", strip=True)))
    if not match:
        return None

    number = int(match.group(1))
    title = clean_text(match.group(2))
    author = ""

    blocks: list[tuple[str, str]] = []
    current_label: int | None = None
    current_lines: list[str] = []

    def flush() -> None:
        nonlocal current_label, current_lines
        if current_label is None:
            return
        text = normalize_block("\\n".join(current_lines))
        if text:
            blocks.append((str(current_label), text))
        current_label = None
        current_lines = []

    # Le contenu d'un article WordPress est situé entre son titre et les
    # métadonnées / le prochain titre de chant.
    node = article_heading.next_sibling
    while node:
        if isinstance(node, Tag):
            classes = " ".join(node.get("class", []))

            if node.name in {"h1", "h2"}:
                break

            if "entry-meta" in classes or "post-meta" in classes:
                meta_text = clean_text(node.get_text(" ", strip=True))
                author_match = re.search(
                    r"(?:Auteur|Author)\\s+(.+?)(?:\\s+Catégories|\\s+Categories|$)",
                    meta_text,
                    re.IGNORECASE,
                )
                if author_match:
                    author = author_match.group(1).strip()
                break

            text = normalize_block(node.get_text("\\n", strip=True))
            if text:
                for raw_line in text.splitlines():
                    line = clean_text(raw_line)

                    # Les références bibliques / Salamo sont conservées dans
                    # le premier bloc afin de ne pas perdre d'information.
                    verse = VERSE_RE.match(line)
                    chorus = CHORUS_RE.match(line)

                    if verse:
                        flush()
                        current_label = int(verse.group(1))
                        remainder = verse.group(2).strip()
                        current_lines = [remainder] if remainder else []
                    elif chorus:
                        flush()
                        current_label = 0
                        remainder = chorus.group(1).strip()
                        current_lines = [remainder] if remainder else []
                    elif current_label is not None:
                        current_lines.append(line)
                    elif line:
                        # Référence avant le premier verset.
                        current_label = 1
                        current_lines.append(line)

        node = node.next_sibling

    flush()

    # Si le HTML du thème ne permet pas de repérer les métadonnées, on
    # laisse mpanoratra vide plutôt que d'inventer une valeur.
    strophes = [
        {
            "andininy": int(label),
            "tononkira": text,
            "fiverenany": int(label) == 0,
        }
        for label, text in blocks
    ]

    if not strophes:
        raise ValueError(f"Aucun contenu de chant détecté pour TS {number}")

    return {
        "key": f"tsanta_{number}",
        "laharana": str(number),
        "sokajy": "tsanta",
        "lohateny": title,
        "mpanoratra": [author] if author else [],
        "hira": strophes,
    }


def extract_page(soup: BeautifulSoup) -> list[dict]:
    songs: list[dict] = []

    for heading in soup.find_all(["h1", "h2"]):
        if not isinstance(heading, Tag):
            continue
        text = clean_text(heading.get_text(" ", strip=True))
        if SONG_RE.match(text):
            song = extract_song(heading)
            if song:
                songs.append(song)

    return songs


def find_next_page(soup: BeautifulSoup, current_url: str) -> str | None:
    for link in soup.find_all("a", href=True):
        label = clean_text(link.get_text(" ", strip=True)).lower()
        rel = " ".join(link.get("rel", [])).lower()
        if "page suivante" in label or "next" in label or "next" in rel:
            return urljoin(current_url, link["href"])
    return None


def scrape(start_url: str, delay: float = 1.0) -> OrderedDict:
    session = requests.Session()
    session.headers.update(HEADERS)

    all_songs: dict[int, dict] = {}
    url = start_url
    visited: set[str] = set()

    while url and url not in visited:
        visited.add(url)
        print(f"[INFO] Scraping: {url}")

        soup = get_soup(session, url)
        page_songs = extract_page(soup)

        for song in page_songs:
            number = int(song["laharana"])
            all_songs[number] = song
            print(f"  [OK] TS {number}: {song['lohateny']}")

        next_url = find_next_page(soup, url)
        if next_url and next_url not in visited:
            url = next_url
            time.sleep(delay)
        else:
            url = None

    if not all_songs:
        raise RuntimeError("Aucun chant TSANTA n'a été trouvé.")

    ordered = OrderedDict()
    for number in sorted(all_songs):
        song = all_songs[number]
        key = song.pop("key")
        ordered[key] = song

    return ordered


def save_json(data: OrderedDict, output: str) -> None:
    with open(output, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=4)
        fh.write("\\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Scraper des chants TSANTA de Fihirana.org")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="Fichier JSON de sortie")
    parser.add_argument("--delay", type=float, default=1.0, help="Délai entre les pages")
    parser.add_argument("--url", default=BASE_URL, help="URL de départ")
    args = parser.parse_args()

    data = scrape(args.url, args.delay)
    save_json(data, args.output)

    print(f"\\n[DONE] {len(data)} chants écrits dans {args.output}")
    print("[INFO] Numéros:", ", ".join(item["laharana"] for item in data.values()))


if __name__ == "__main__":
    main()
