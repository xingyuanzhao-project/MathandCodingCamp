#!/usr/bin/env python3
"""Generate the modules landing page from modules/catalog.json."""

from __future__ import annotations

import html
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "modules" / "catalog.json"
OUTPUT_PATH = ROOT / "modules" / "index.html"


def item_href(item: dict[str, str], catalog: dict) -> str | None:
    if "href" in item:
        return item["href"]
    if "hrefKey" in item:
        return catalog["links"][item["hrefKey"]]
    return None


def render_items(items: list[dict[str, str]], catalog: dict) -> str:
    rendered: list[str] = []
    for item in items:
        label = html.escape(item["label"])
        href = item_href(item, catalog)
        if href is None:
            rendered.append(f"                        <li>{label}</li>")
            continue
        css_class = (
            f' class="{html.escape(item["class"], quote=True)}"'
            if "class" in item
            else ""
        )
        rendered.append(
            f'                        <li><a href="{html.escape(href, quote=True)}"{css_class}>{label}</a></li>'
        )
    return "\n".join(rendered)


def render_day(day: dict, catalog: dict) -> str:
    sessions: list[str] = []
    for session in day["sessions"]:
        sessions.append(
            "\n".join(
                [
                    "            <li>",
                    f"                <h3>{html.escape(session['label'])}</h3>",
                    "                <ul>",
                    render_items(session["items"], catalog),
                    "                </ul>",
                    "            </li>",
                ]
            )
        )
    return "\n".join(
        [
            f"        <h2>{html.escape(day['label'])}</h2>",
            "        <nav>",
            "            <ul>",
            "\n".join(sessions),
            "            </ul>",
            "        </nav>",
        ]
    )


def render_resource(section: dict, catalog: dict) -> str:
    return "\n".join(
        [
            f"        <h2>{html.escape(section['label'])}</h2>",
            "        <nav>",
            "            <ul>",
            render_items(section["items"], catalog),
            "            </ul>",
            "        </nav>",
        ]
    )


def render(catalog: dict) -> str:
    sections = [render_day(day, catalog) for day in catalog["days"]]
    sections.extend(render_resource(section, catalog) for section in catalog["resources"])
    title = html.escape(catalog["title"])
    body = "\n".join(sections)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <link rel="stylesheet" href="../assets/css/site.css">
</head>
<body>
<header>
    <img src="../assets/brand/epps-logo.png" alt="EPPS Logo" class="logo">
    <h1>{title}</h1>
    <a href="../" class="main-site-link">Main Website</a>
</header>
<main>
{body}
</main>
<footer>
    <p>&copy; Math and Coding Camp - EPPS</p>
    <p>Made with ❤️ by <a href="https://github.com/shreyasmeher" target="_blank" rel="noopener noreferrer">Shreyas Meher</a> and Xingyuan Zhao</p>
</footer>
</body>
</html>
"""


def main() -> None:
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    OUTPUT_PATH.write_text(render(catalog), encoding="utf-8")


if __name__ == "__main__":
    main()
