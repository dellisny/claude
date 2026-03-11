#!/usr/bin/env python3
"""headlines — Bloomberg-style top news digest from major outlets."""

import sys
import time
import feedparser
import requests
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from zoneinfo import ZoneInfo

from rich.console import Console
from rich.text import Text
from rich.rule import Rule
from rich import print as rprint

SOURCES = [
    {
        "name": "NYT",
        "label": "NYT    ",
        "color": "bright_white",
        "url": "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml",
    },
    {
        "name": "MKTWTCH",
        "label": "MKTWTCH",
        "color": "bright_cyan",
        "url": "https://feeds.marketwatch.com/marketwatch/topstories/",
    },
    {
        "name": "FT",
        "label": "FT     ",
        "color": "bright_yellow",
        "url": "https://www.ft.com/?format=rss",
    },
    {
        "name": "REUTERS",
        "label": "REUTERS",
        "color": "bright_red",
        "url": "https://feeds.reuters.com/reuters/topNews",
    },
    {
        "name": "BBC",
        "label": "BBC    ",
        "color": "cyan",
        "url": "https://feeds.bbci.co.uk/news/rss.xml",
    },
    {
        "name": "GUARD",
        "label": "GUARD  ",
        "color": "green",
        "url": "https://www.theguardian.com/world/rss",
    },
    {
        "name": "NY POST",
        "label": "NY POST",
        "color": "bright_magenta",
        "url": "https://nypost.com/feed/",
    },
    {
        "name": "ECONMST",
        "label": "ECONMST",
        "color": "bright_red",
        "url": "https://www.economist.com/the-world-this-week/rss.xml",
    },
    {
        "name": "AP",
        "label": "AP     ",
        "color": "white",
        "url": "https://feeds.apnews.com/rss/apf-topnews",
    },
]

ET = ZoneInfo("America/New_York")
FETCH_TIMEOUT = 8  # seconds per feed
MAX_PER_SOURCE = 6  # candidates per source before dedup


def fetch_feed(source: dict) -> list[dict]:
    """Fetch and parse one RSS feed; return list of story dicts."""
    try:
        resp = requests.get(
            source["url"],
            timeout=FETCH_TIMEOUT,
            headers={"User-Agent": "Mozilla/5.0 (headlines/1.0)"},
        )
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
        stories = []
        for entry in feed.entries[:MAX_PER_SOURCE]:
            title = entry.get("title", "").strip()
            if not title:
                continue
            # Parse publish time
            pub = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                pub = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            stories.append(
                {
                    "source": source["name"],
                    "label": source["label"],
                    "color": source["color"],
                    "title": title,
                    "pub": pub,
                    "url": entry.get("link", ""),
                }
            )
        return stories
    except Exception:
        return []


def relative_time(pub: datetime | None) -> str:
    if pub is None:
        return "      "
    now = datetime.now(timezone.utc)
    delta = int((now - pub).total_seconds())
    if delta < 60:
        return f"{delta}s ago"
    if delta < 3600:
        return f"{delta // 60}m ago"
    if delta < 86400:
        return f"{delta // 3600}h ago"
    return f"{delta // 86400}d ago"


def fetch_all() -> list[dict]:
    """Fetch all sources in parallel and return merged, deduplicated stories."""
    all_stories = []
    with ThreadPoolExecutor(max_workers=len(SOURCES)) as pool:
        futures = {pool.submit(fetch_feed, src): src for src in SOURCES}
        for future in as_completed(futures):
            all_stories.extend(future.result())

    # Sort: stories with timestamps first (newest first), then un-timestamped
    timestamped = [s for s in all_stories if s["pub"]]
    no_time = [s for s in all_stories if not s["pub"]]
    timestamped.sort(key=lambda s: s["pub"], reverse=True)

    return timestamped + no_time


def dedup(stories: list[dict], count: int, max_per_source: int = 2) -> list[dict]:
    """Pick `count` stories, skipping near-duplicates and capping per source."""
    seen_words: list[set] = []
    source_counts: dict[str, int] = {}
    selected = []

    for story in stories:
        src = story["source"]
        if source_counts.get(src, 0) >= max_per_source:
            continue
        words = set(story["title"].lower().split())
        # Skip if >50% word overlap with an already-selected headline
        duplicate = any(
            len(words & seen) / max(len(words | seen), 1) > 0.5
            for seen in seen_words
        )
        if not duplicate:
            selected.append(story)
            seen_words.append(words)
            source_counts[src] = source_counts.get(src, 0) + 1
        if len(selected) >= count:
            break

    return selected


def render(stories: list[dict], count: int):
    console = Console()
    now_et = datetime.now(ET)
    timestamp = now_et.strftime("%a %d %b %Y  %H:%M ET")

    # Header bar
    console.print()
    header = Rule(
        f"[bold bright_yellow] HEADLINES [/]  [dim]{timestamp}[/]",
        style="bright_yellow",
        characters="━",
    )
    console.print(header)
    console.print()

    w = console.width
    age_col = 8   # " 12m ago"
    index_col = 4  # " 1  "
    tag_col = 9   # " NYT     "
    gap = 2       # "  " before title
    link_col = 6  # " link "
    max_title = w - index_col - tag_col - gap - link_col - age_col - 1

    # Stories
    for i, story in enumerate(stories, 1):
        source_tag = Text(f" {story['label']} ", style=f"bold {story['color']} on grey11")
        age = relative_time(story["pub"])
        age_text = Text(f"  {age:>6}", style="dim")

        # Truncate title to fit on one line
        title = story["title"]
        if len(title) > max_title:
            title = title[: max_title - 1] + "…"

        line = Text(no_wrap=True, overflow="ellipsis")
        line.append(f"{i:>2}  ", style="dim")
        line.append_text(source_tag)
        line.append(f"  {title:<{max_title}}", style="bright_white")
        if story.get("url"):
            line.append(" link ", style=f"dim cyan link {story['url']}")
        else:
            line.append(" " * link_col)
        line.append_text(age_text)

        console.print(line)

        # Thin separator between items
        if i < len(stories):
            console.print(Text("    " + "─" * (w - 5), style="grey23"))

    console.print()
    console.print(Rule(style="bright_yellow", characters="━"))
    console.print(
        f"[dim]  {len(stories)} headlines from {len(set(s['source'] for s in stories))} sources[/]"
    )
    console.print()


def filter_by_keyword(stories: list[dict], keyword: str) -> list[dict]:
    """Return stories whose title contains the keyword (case-insensitive)."""
    kw = keyword.lower()
    return [s for s in stories if kw in s["title"].lower()]


def main():
    count = 20
    keyword = None

    if len(sys.argv) > 1:
        arg = sys.argv[1]
        try:
            count = int(arg)
        except ValueError:
            keyword = arg

    console = Console()
    with console.status("[bold bright_yellow]Fetching headlines...[/]"):
        stories = fetch_all()

    if keyword:
        top = filter_by_keyword(stories, keyword)
    else:
        top = dedup(stories, count, max_per_source=3)

    if not top:
        if keyword:
            console.print(f"[red]No headlines found matching '{keyword}'.[/]")
        else:
            console.print("[red]No headlines retrieved. Check your connection.[/]")
        sys.exit(1)

    render(top, count)


if __name__ == "__main__":
    main()
