#!/usr/bin/env python3
"""
Scraper des chants TSANTA depuis Fihirana.org.

Génère 04_tsanta.json avec la même structure que les autres données
du dépôt Fihirana-FFPM.

Dépendances:
    python -m pip install requests beautifulsoup4

Sur Arch/CachyOS, si pip n'est pas installé:
    sudo pacman -S python-pip
    python -m pip install requests beautifulsoup4
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
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120 Safari/537.36 "
        "Fihirana-FFPM-TSANTA-scraper/1.0"
    )
}

SONG_RE = re.compile(r"^TS\s*(\d+)\s*[–—-]\s*(.+)$", re.IGNORECASE)
VERSE_RE = re.compile(r"^(\d+)\s*\.\s*(.*)$")
CHORUS_RE = re.compile(r"^Fiv\s*:?\s*(.*)$", re.IGNORECASE)


def clean_text(text: str) -> str:
    """Nettoie un texte sans supprimer les accents malgaches."""
    text = text.replace("\xa0", " ")
    text = text.replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    return text.strip()


def normalize_lines(text: str) -> list[str]:
    """Transforme le texte HTML en lignes propres."""
    result = []
    for raw in text.splitlines():
        line = clean_text(raw)
        if line:
            result.append(line)
    return result


def get_soup(session: requests.Session, url: str) -> BeautifulSoup:
    response = session.get(url, timeout=30)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding
    return BeautifulSoup(response.text, "html.parser")


def find_article(heading: Tag) -> Tag | None:
    """Trouve le conteneur WordPress correspondant au titre du chant."""
    article = heading.find_parent("article")
    if isinstance(article, Tag):
        return article

    # Fallback pour un thème qui n'utilise pas <article>.
    parent = heading.parent
    if isinstance(parent, Tag):
        return parent

    return None


def extract_song(heading: Tag) -> dict | None:
    """Extrait un chant à partir de son titre TS."""
    heading_text = clean_text(heading.get_text(" ", strip=True))
    match = SONG_RE.match(heading_text)
    if not match:
        return None

    number = int(match.group(1))
    title = clean_text(match.group(2))

    article = find_article(heading)
    if article is None:
        return None

    content = article.select_one(
        ".entry-content, .post-content, .article-content, .content"
    )

    if not isinstance(content, Tag):
        content = article

    # On retire les éléments qui ne font pas partie des paroles.
    for unwanted in content.select(
        "script, style, nav, .entry-meta, .post-meta, .post-footer"
    ):
        unwanted.decompose()

    lines = normalize_lines(content.get_text("\n", strip=True))

    # Retirer le titre TS s'il apparaît aussi dans le contenu.
    if lines and SONG_RE.match(lines[0]):
        lines.pop(0)

    blocks: list[tuple[int, list[str]]] = []
    current_number: int | None = None
    current_lines: list[str] = []

    def flush() -> None:
        nonlocal current_number, current_lines
        if current_number is None:
            return

        text_lines = [line for line in current_lines if line]
        if text_lines:
            blocks.append((current_number, text_lines))

        current_number = None
        current_lines = []

    for line in lines:
        verse = VERSE_RE.match(line)
        chorus = CHORUS_RE.match(line)

        if verse:
            flush()
            current_number = int(verse.group(1))
            remainder = verse.group(2).strip()
            current_lines = [remainder] if remainder else []
            continue

        if chorus:
            flush()
            current_number = 0
            remainder = chorus.group(1).strip()
            current_lines = [remainder] if remainder else []
            continue

        if current_number is None:
            # Référence biblique ou texte introductif avant le premier verset.
            current_number = 1

        current_lines.append(line)

    flush()

    if not blocks:
        raise ValueError(f"Impossible d'extraire le contenu de TS {number}")

    hira = [
        {
            "andininy": verse_number,
            "tononkira": "\n".join(text_lines),
            "fiverenany": verse_number == 0,
        }
        for verse_number, text_lines in blocks
    ]

    return {
        "key": f"tsanta_{number}",
        "laharana": str(number),
        "sokajy": "tsanta",
        "lohateny": title,
        "mpanoratra": [],
        "hira": hira,
    }


def extract_page(soup: BeautifulSoup) -> list[dict]:
    """Extrait tous les chants TS trouvés sur une page de catégorie."""
    songs = []

    for heading in soup.find_all(["h1", "h2", "h3"]):
        if not isinstance(heading, Tag):
            continue

        text = clean_text(heading.get_text(" ", strip=True))
        if not SONG_RE.match(text):
            continue

        try:
            song = extract_song(heading)
            if song:
                songs.append(song)
        except ValueError as exc:
            print(f"[WARN] {exc}")

    return songs


def find_next_page(soup: BeautifulSoup, current_url: str) -> str | None:
    """Trouve le lien de pagination WordPress."""
    selectors = [
        "a.next",
        "a.next.page-numbers",
        "a.nav-next",
        "a.nextpostslink",
        "a[rel='next']",
    ]

    for selector in selectors:
        link = soup.select_one(selector)
        if isinstance(link, Tag) and link.get("href"):
            return urljoin(current_url, str(link["href"]))

    # Fallback: recherche textuelle.
    for link in soup.find_all("a", href=True):
        label = clean_text(link.get_text(" ", strip=True)).lower()
        if label in {"next", "suivant", "page suivante", "older posts"}:
            return urljoin(current_url, str(link["href"]))

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

        print(f"[INFO] {len(page_songs)} chant(s) trouvé(s) sur cette page.")

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
        raise RuntimeError(
            "Aucun chant TSANTA n'a été trouvé. "
            "Vérifiez l'accès à fihirana.org et la structure HTML du site."
        )

    ordered = OrderedDict()

    for number in sorted(all_songs):
        song = all_songs[number]
        key = song.pop("key")
        ordered[key] = song

    return ordered


def save_json(data: OrderedDict, output: str) -> None:
    with open(output, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=4)
        fh.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scrape les chants TSANTA de Fihirana.org"
    )
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT,
        help="Fichier JSON de sortie (défaut: 04_tsanta.json)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Délai entre les pages en secondes",
    )
    parser.add_argument(
        "--url",
        default=BASE_URL,
        help="URL de départ",
    )
    args = parser.parse_args()

    data = scrape(args.url, args.delay)
    save_json(data, args.output)

    print()
    print(f"[DONE] {len(data)} chants écrits dans {args.output}")
    print(
        "[INFO] Numéros:",
        ", ".join(item["laharana"] for item in data.values()),
    )


if __name__ == "__main__":
    main()
