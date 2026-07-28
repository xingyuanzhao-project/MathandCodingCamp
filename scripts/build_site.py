#!/usr/bin/env python3
"""Build the camp site from the manager's navigation hierarchy.

settings/site-map.yml is intentionally small. It contains headings, nested
headings, and leaf items. A leaf can point to a contributor page file, a
static downloadable file, an existing URL, or no target at all.
"""

from __future__ import annotations

import argparse
import html
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC_ROOT = ROOT / "static"
MODULES_ROOT = ROOT / "modules"
MAP_PATH = ROOT / "settings" / "site-map.yml"
PAGE_SUFFIXES = {".html", ".qmd", ".rmd"}
DOWNLOAD_SUFFIXES = {".csv", ".xlsx", ".xls", ".pptx"}


class BuildError(RuntimeError):
    """Raised when the site map or source layout cannot be built safely."""


@dataclass(frozen=True)
class SourceLine:
    line_number: int
    indent: int
    text: str


@dataclass(frozen=True)
class Item:
    label: str
    target: str | None


@dataclass
class Heading:
    label: str
    headings: list["Heading"] | None = None
    items: list[Item] | None = None


@dataclass(frozen=True)
class Page:
    name: str
    source: Path
    output_directory: Path


@dataclass(frozen=True)
class ResolvedItem:
    label: str
    href: str | None
    css_class: str | None


@dataclass
class ResolvedHeading:
    label: str
    headings: list["ResolvedHeading"] | None = None
    items: list[ResolvedItem] | None = None


def indentation(line: str) -> int:
    prefix = line[: len(line) - len(line.lstrip(" \t"))]
    if "\t" in prefix:
        raise BuildError("settings/site-map.yml must use spaces, not tabs.")
    return len(prefix)


def unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def split_pair(value: str) -> tuple[str, str] | None:
    """Split a simple YAML key/value pair at its first unquoted colon."""
    quote: str | None = None
    for index, character in enumerate(value):
        if character in {"'", '"'}:
            if quote is None:
                quote = character
            elif quote == character:
                quote = None
        elif character == ":" and quote is None:
            return value[:index].strip(), value[index + 1 :].strip()
    return None


def source_lines(path: Path) -> list[SourceLine]:
    if not path.is_file():
        raise BuildError(f"Missing manager file: {path.relative_to(ROOT)}")

    lines: list[SourceLine] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        text = raw_line.strip()
        if not text or text.startswith("#"):
            continue
        lines.append(SourceLine(line_number, indentation(raw_line), text))
    return lines


def parse_items(lines: list[SourceLine], index: int, indent: int) -> tuple[list[Item], int]:
    items: list[Item] = []
    while index < len(lines) and lines[index].indent == indent:
        line = lines[index]
        if not line.text.startswith("- "):
            break

        item_text = line.text[2:].strip()
        if not item_text:
            raise BuildError(f"Empty item at {MAP_PATH.name}:{line.line_number}")

        pair = split_pair(item_text)
        if pair is None:
            items.append(Item(label=unquote(item_text), target=None))
        else:
            label, target = (unquote(part) for part in pair)
            if not label or not target:
                raise BuildError(
                    f"Empty item label or target at {MAP_PATH.name}:{line.line_number}"
                )
            items.append(Item(label=label, target=target))
        index += 1

    if not items:
        line = lines[index] if index < len(lines) else lines[-1]
        raise BuildError(f"Expected a list at {MAP_PATH.name}:{line.line_number}")
    return items, index


def parse_headings(
    lines: list[SourceLine], index: int, indent: int
) -> tuple[list[Heading], int]:
    headings: list[Heading] = []
    while index < len(lines) and lines[index].indent == indent:
        line = lines[index]
        if line.text.startswith("- "):
            break

        pair = split_pair(line.text)
        if pair is None or pair[1]:
            raise BuildError(
                f"Headings must end with ':' at {MAP_PATH.name}:{line.line_number}"
            )
        label = unquote(pair[0])
        if not label:
            raise BuildError(f"Empty heading at {MAP_PATH.name}:{line.line_number}")

        index += 1
        if index >= len(lines) or lines[index].indent <= indent:
            raise BuildError(
                f"Heading {label!r} has no contents at {MAP_PATH.name}:{line.line_number}"
            )

        child_indent = lines[index].indent
        if lines[index].text.startswith("- "):
            items, index = parse_items(lines, index, child_indent)
            headings.append(Heading(label=label, items=items))
        else:
            children, index = parse_headings(lines, index, child_indent)
            headings.append(Heading(label=label, headings=children))

    return headings, index


def parse_site_map(path: Path) -> list[Heading]:
    lines = source_lines(path)
    if not lines:
        raise BuildError(f"{path.relative_to(ROOT)} has no headings.")

    headings, index = parse_headings(lines, 0, lines[0].indent)
    if index != len(lines):
        line = lines[index]
        raise BuildError(f"Cannot read {path.name}:{line.line_number}: {line.text}")
    return headings


def walk_items(headings: list[Heading]) -> list[Item]:
    items: list[Item] = []
    for heading in headings:
        if heading.items is not None:
            items.extend(heading.items)
        elif heading.headings is not None:
            items.extend(walk_items(heading.headings))
    return items


def is_external(target: str) -> bool:
    return target.startswith(("https://", "http://", "mailto:"))


def discover_page(name: str) -> Page:
    if Path(name).name != name:
        raise BuildError(f"Use a contributor filename, not a path: {name}")
    matches = [candidate for candidate in MODULES_ROOT.rglob(name) if candidate.is_file()]
    if not matches:
        raise BuildError(
            f"{MAP_PATH.relative_to(ROOT)} names {name}, but no contributor page has that name."
        )
    if len(matches) > 1:
        paths = ", ".join(str(candidate.relative_to(ROOT)) for candidate in sorted(matches))
        raise BuildError(
            f"{name} is ambiguous below modules/: {paths}. "
            "Contributor page filenames must be unique."
        )

    source = matches[0]
    entry_files = [
        candidate
        for candidate in source.parent.iterdir()
        if candidate.is_file() and candidate.suffix.lower() in PAGE_SUFFIXES
    ]
    if entry_files != [source]:
        found = ", ".join(candidate.name for candidate in sorted(entry_files))
        raise BuildError(
            f"{source.parent.relative_to(ROOT)} must contain exactly one page entry "
            f"(.html, .qmd, or .Rmd); found: {found or 'none'}."
        )

    return Page(
        name=name,
        source=source,
        output_directory=source.parent.relative_to(MODULES_ROOT),
    )


def discover_pages(headings: list[Heading]) -> dict[str, Page]:
    if not MODULES_ROOT.is_dir():
        raise BuildError(f"Missing modules directory: {MODULES_ROOT.relative_to(ROOT)}")

    pages: dict[str, Page] = {}
    for item in walk_items(headings):
        if item.target is None or is_external(item.target):
            continue
        if Path(item.target).suffix.lower() in PAGE_SUFFIXES:
            if item.target not in pages:
                pages[item.target] = discover_page(item.target)
    return pages


def static_href(filename: str) -> str:
    if Path(filename).name != filename:
        raise BuildError(f"Use a static filename, not a path: {filename}")
    matches = [
        candidate
        for source_root in (MODULES_ROOT, STATIC_ROOT)
        if source_root.is_dir()
        for candidate in source_root.rglob(filename)
        if candidate.is_file()
    ]
    if not matches:
        raise BuildError(
            f"{MAP_PATH.relative_to(ROOT)} names {filename}, but no static file has that name."
        )
    if len(matches) > 1:
        paths = ", ".join(str(candidate.relative_to(ROOT)) for candidate in sorted(matches))
        raise BuildError(
            f"{filename} is ambiguous below modules/ and static/: {paths}. "
            "Static filenames listed in the map must be unique."
        )

    source = matches[0]
    if source.is_relative_to(MODULES_ROOT):
        return source.relative_to(MODULES_ROOT).as_posix()
    return (Path("..") / source.relative_to(STATIC_ROOT)).as_posix()


def page_href(page: Page) -> str:
    relative = page.output_directory.as_posix()
    return f"{relative}/" if relative != "." else "./"


def resolve_item(item: Item, pages: dict[str, Page]) -> ResolvedItem:
    if item.target is None:
        return ResolvedItem(label=item.label, href=None, css_class=None)

    target = item.target
    if target.startswith("mailto:"):
        return ResolvedItem(label=item.label, href=target, css_class="upload-link")
    if target.startswith(("https://", "http://")):
        return ResolvedItem(label=item.label, href=target, css_class=None)

    suffix = Path(target).suffix.lower()
    if suffix in PAGE_SUFFIXES:
        return ResolvedItem(label=item.label, href=page_href(pages[target]), css_class=None)

    css_class = "download-link" if suffix in DOWNLOAD_SUFFIXES else None
    return ResolvedItem(label=item.label, href=static_href(target), css_class=css_class)


def resolve_headings(
    headings: list[Heading], pages: dict[str, Page]
) -> list[ResolvedHeading]:
    resolved: list[ResolvedHeading] = []
    for heading in headings:
        if heading.items is not None:
            resolved.append(
                ResolvedHeading(
                    label=heading.label,
                    items=[resolve_item(item, pages) for item in heading.items],
                )
            )
        elif heading.headings is not None:
            resolved.append(
                ResolvedHeading(
                    label=heading.label,
                    headings=resolve_headings(heading.headings, pages),
                )
            )
    return resolved


def clean_output(output: Path) -> None:
    if output.resolve() == ROOT.resolve():
        raise BuildError("Refusing to use the repository root as build output.")
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)


def copy_static_site(output: Path) -> None:
    if not STATIC_ROOT.is_dir():
        raise BuildError(f"Missing static source directory: {STATIC_ROOT.relative_to(ROOT)}")
    shutil.copytree(STATIC_ROOT, output, dirs_exist_ok=True)


def copy_module_static_files(output: Path, pages: dict[str, Page]) -> None:
    """Copy non-page module files while leaving listed page folders to their renderer."""
    if not MODULES_ROOT.is_dir():
        raise BuildError(f"Missing modules directory: {MODULES_ROOT.relative_to(ROOT)}")

    page_directories = tuple(page.source.parent for page in pages.values())
    for source in MODULES_ROOT.rglob("*"):
        if not source.is_file() or any(
            source.is_relative_to(page_directory) for page_directory in page_directories
        ):
            continue
        destination = output / "modules" / source.relative_to(MODULES_ROOT)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def copy_page_support_files(page: Page, output_directory: Path) -> None:
    output_directory.mkdir(parents=True, exist_ok=True)
    for item in page.source.parent.iterdir():
        if item == page.source:
            continue
        destination = output_directory / item.name
        if item.is_dir():
            shutil.copytree(item, destination, dirs_exist_ok=True)
        else:
            shutil.copy2(item, destination)


def render_page(page: Page, output: Path) -> None:
    output_directory = output / "modules" / page.output_directory
    if page.source.suffix.lower() == ".html":
        copy_page_support_files(page, output_directory)
        shutil.copy2(page.source, output_directory / "index.html")
        return

    with tempfile.TemporaryDirectory(prefix="math-camp-page-") as temporary:
        staging_directory = Path(temporary) / "page"
        shutil.copytree(page.source.parent, staging_directory)
        staged_source = staging_directory / page.source.name
        command = [
            "quarto",
            "render",
            staged_source.name,
            "--to",
            "html",
            "--output",
            "index.html",
        ]
        try:
            subprocess.run(command, check=True, cwd=staging_directory)
        except FileNotFoundError as error:
            raise BuildError("Quarto is required to render .qmd and .Rmd files.") from error
        except subprocess.CalledProcessError as error:
            raise BuildError(f"Could not render {page.source}.") from error

        output_directory.mkdir(parents=True, exist_ok=True)
        source_artifacts = {
            staged_source,
            staging_directory / f"{staged_source.stem}.knit.md",
        }
        for item in staging_directory.iterdir():
            if item in source_artifacts:
                continue
            destination = output_directory / item.name
            if item.is_dir():
                shutil.copytree(item, destination, dirs_exist_ok=True)
            else:
                shutil.copy2(item, destination)

    if not (output_directory / "index.html").is_file():
        raise BuildError(f"Quarto completed without creating {output_directory / 'index.html'}.")


def render_leaf(item: ResolvedItem) -> str:
    if item.href is None:
        return f"            <li>{html.escape(item.label)}</li>"

    css = (
        f' class="{html.escape(item.css_class, quote=True)}"'
        if item.css_class
        else ""
    )
    return (
        f'            <li><a href="{html.escape(item.href, quote=True)}"{css}>'
        f"{html.escape(item.label)}</a></li>"
    )


def render_branch(heading: ResolvedHeading, level: int) -> str:
    heading_tag = f"h{min(level, 6)}"
    title = f"<{heading_tag}>{html.escape(heading.label)}</{heading_tag}>"
    if heading.items is not None:
        leaves = "\n".join(render_leaf(item) for item in heading.items)
        return "\n".join([title, "                <ul>", leaves, "                </ul>"])

    if heading.headings is None:
        raise BuildError(f"Heading {heading.label!r} has no contents.")
    children = "\n".join(
        "\n".join(
            [
                "            <li>",
                *[
                    f"                {line}" if line else line
                    for line in render_branch(child, level + 1).splitlines()
                ],
                "            </li>",
            ]
        )
        for child in heading.headings
    )
    return "\n".join([title, "                <ul>", children, "                </ul>"])


def render_top_level(heading: ResolvedHeading) -> str:
    if heading.items is not None:
        items = "\n".join(render_leaf(item) for item in heading.items)
    elif heading.headings is not None:
        items = "\n".join(
            "\n".join(
                [
                    "        <li>",
                    *[
                        f"            {line}" if line else line
                        for line in render_branch(child, 3).splitlines()
                    ],
                    "        </li>",
                ]
            )
            for child in heading.headings
        )
    else:
        raise BuildError(f"Heading {heading.label!r} has no contents.")

    return "\n".join(
        [
            f"        <h2>{html.escape(heading.label)}</h2>",
            "        <nav>",
            "            <ul>",
            items,
            "            </ul>",
            "        </nav>",
        ]
    )


def navigation_html(headings: list[ResolvedHeading]) -> str:
    body = "\n".join(render_top_level(heading) for heading in headings)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>EPPS Math &amp; Coding Camp</title>
    <link rel="stylesheet" href="../assets/css/site.css">
</head>
<body>
<header>
    <img src="../assets/brand/epps-logo.png" alt="EPPS Logo" class="logo">
    <h1>EPPS Math &amp; Coding Camp</h1>
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


def write_modules_page(output: Path, headings: list[ResolvedHeading]) -> None:
    destination = output / "modules" / "index.html"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(navigation_html(headings), encoding="utf-8")


def build(output: Path) -> None:
    headings = parse_site_map(MAP_PATH)
    pages = discover_pages(headings)
    resolved = resolve_headings(headings, pages)

    clean_output(output)
    copy_static_site(output)
    copy_module_static_files(output, pages)
    for page in pages.values():
        render_page(page, output)
    write_modules_page(output, resolved)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the site from settings/site-map.yml and contributor pages."
    )
    parser.add_argument(
        "--output",
        default="_site",
        help="Generated site directory, relative to the repository root (default: _site).",
    )
    args = parser.parse_args()
    output = (ROOT / args.output).resolve()

    try:
        build(output)
    except BuildError as error:
        print(f"Build failed: {error}", file=sys.stderr)
        return 1

    print(f"Built {output.relative_to(ROOT)} from {MAP_PATH.relative_to(ROOT)}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
