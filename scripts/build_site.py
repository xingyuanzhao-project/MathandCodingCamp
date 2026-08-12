#!/usr/bin/env python3
"""Build the camp site from the manager's navigation hierarchy.

settings/site-map.yml is intentionally small. It contains headings, nested
headings, and leaf items. A leaf can point to a contributor page file, a
static downloadable file, an existing URL, or no target at all.

Every local leaf target is an explicit path, relative to the repository
root (for example "modules/math/day-1/preliminaries/day-1-preliminaries.html").
There is no filename search: the build fails loudly if the named path does
not exist, instead of guessing at a match.

Before deleting an existing output, the builder intakes each contributor HTML
package. A literal local HTML resource path is its required output destination.
If that exact path is absent from the supplied package, the builder can copy
one uniquely named supplied file to that destination. Zero or multiple exact
filename candidates fail the build; names, folder names, and path suffixes are
never treated as equivalent.

A heading (`Day 1:`, etc.) may optionally carry a path prefix after its
colon (for example `Day 1: modules/math/day-1`). When present, every leaf
nested under that heading must resolve to a path under that prefix, so the
heading is an enforced constraint, not just display text. The label itself
is still exactly what a visitor sees; the prefix is never rendered.
"""

from __future__ import annotations

import argparse
import html
import shutil
import sys
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote as url_unquote
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
STATIC_ROOT = ROOT / "static"
MODULES_ROOT = ROOT / "modules"
MAP_PATH = ROOT / "settings" / "site-map.yml"
PAGE_SUFFIXES = {".html"}
DOWNLOAD_SUFFIXES = {".csv", ".xlsx", ".xls", ".pptx"}
RESOURCE_ATTRIBUTES = {
    "audio": ("src",),
    "embed": ("src",),
    "iframe": ("src",),
    "img": ("src", "data-src", "srcset"),
    "link": ("href",),
    "object": ("data",),
    "script": ("src",),
    "source": ("src", "srcset"),
    "track": ("src",),
    "video": ("src", "poster"),
}


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
    path_prefix: str | None = None
    headings: list["Heading"] | None = None
    items: list[Item] | None = None


@dataclass(frozen=True)
class Page:
    name: str
    source: Path
    output_directory: Path


@dataclass(frozen=True)
class AssetMove:
    """Copy one uniquely identified source file to HTML's required path."""

    source: Path
    destination: Path


@dataclass(frozen=True)
class PageIntake:
    """Validated output-only asset moves for one contributor page."""

    asset_moves: tuple[AssetMove, ...]


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


class HTMLDependencyParser(HTMLParser):
    """Collect resource URLs without treating navigation links as assets."""

    def __init__(self) -> None:
        super().__init__()
        self.references: list[str] = []

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        self._collect_attributes(tag, attrs)

    def handle_startendtag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        self._collect_attributes(tag, attrs)

    def _collect_attributes(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        attributes = {name.lower(): value for name, value in attrs if value is not None}
        for attribute in RESOURCE_ATTRIBUTES.get(tag.lower(), ()):
            value = attributes.get(attribute)
            if value is None:
                continue
            if attribute == "srcset":
                self._collect_srcset(value)
            else:
                self.references.append(value)

    def _collect_srcset(self, value: str) -> None:
        if value.lstrip().startswith("data:"):
            return
        for candidate in value.split(","):
            url = candidate.strip().split(maxsplit=1)[0]
            if url:
                self.references.append(url)


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
        if pair is None:
            raise BuildError(
                f"Headings must end with ':' at {MAP_PATH.name}:{line.line_number}"
            )
        label = unquote(pair[0])
        if not label:
            raise BuildError(f"Empty heading at {MAP_PATH.name}:{line.line_number}")
        path_prefix = unquote(pair[1]) if pair[1] else None

        index += 1
        if index >= len(lines) or lines[index].indent <= indent:
            raise BuildError(
                f"Heading {label!r} has no contents at {MAP_PATH.name}:{line.line_number}"
            )

        child_indent = lines[index].indent
        if lines[index].text.startswith("- "):
            items, index = parse_items(lines, index, child_indent)
            headings.append(Heading(label=label, path_prefix=path_prefix, items=items))
        else:
            children, index = parse_headings(lines, index, child_indent)
            headings.append(
                Heading(label=label, path_prefix=path_prefix, headings=children)
            )

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


def validate_path_prefixes(
    headings: list[Heading], active_prefixes: tuple[str, ...] = ()
) -> None:
    """Fail loudly if a leaf's path does not fall under an ancestor heading's prefix.

    A heading's path_prefix is an enforced constraint, not a search hint: every
    local target nested under it must resolve under that folder, or the build
    stops here instead of silently accepting a mismatched path.
    """
    for heading in headings:
        prefixes = active_prefixes + ((heading.path_prefix,) if heading.path_prefix else ())
        if heading.items is not None:
            for item in heading.items:
                if item.target is None or is_external(item.target):
                    continue
                target_path = Path(item.target)
                for prefix in prefixes:
                    if not target_path.is_relative_to(Path(prefix)):
                        raise BuildError(
                            f"{MAP_PATH.relative_to(ROOT)}: {item.label!r} targets "
                            f"{item.target!r}, but heading {heading.label!r} requires "
                            f"paths under {prefix}/."
                        )
        elif heading.headings is not None:
            validate_path_prefixes(heading.headings, prefixes)


def resolve_local_path(target: str) -> Path:
    """Resolve a site-map target that is an explicit path from the repository root.

    This performs no search and no fallback: the path is joined directly onto
    the repository root and must exist, or the build fails with the exact
    target that was requested.
    """
    if Path(target).is_absolute():
        raise BuildError(
            f"{MAP_PATH.relative_to(ROOT)} names {target!r}; paths must be relative to "
            "the repository root, not absolute."
        )
    candidate = (ROOT / target).resolve()
    if not candidate.is_relative_to(ROOT):
        raise BuildError(f"{MAP_PATH.relative_to(ROOT)} path escapes the repository: {target}")
    if not candidate.is_file():
        raise BuildError(f"{MAP_PATH.relative_to(ROOT)} names {target!r}, but that file does not exist.")
    return candidate


def discover_page(target: str) -> Page:
    if Path(target).suffix.lower() not in PAGE_SUFFIXES:
        raise BuildError(f"{MAP_PATH.relative_to(ROOT)} page target must end in .html: {target}")

    source = resolve_local_path(target)
    if not source.is_relative_to(MODULES_ROOT):
        raise BuildError(
            f"{MAP_PATH.relative_to(ROOT)} page target must live under modules/: {target}"
        )

    return Page(
        name=target,
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


def static_href(target: str) -> str:
    source = resolve_local_path(target)
    if source.is_relative_to(MODULES_ROOT):
        return source.relative_to(MODULES_ROOT).as_posix()
    if STATIC_ROOT.is_dir() and source.is_relative_to(STATIC_ROOT):
        return (Path("..") / source.relative_to(STATIC_ROOT)).as_posix()
    raise BuildError(
        f"{MAP_PATH.relative_to(ROOT)} static target must live under modules/ or static/: {target}"
    )


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


def local_dependency_path(reference: str) -> Path | None:
    """Return a local resource path without inventing a replacement path."""

    parsed = urlsplit(reference.strip())
    if parsed.scheme or parsed.netloc or not parsed.path:
        return None

    raw_path = url_unquote(parsed.path)
    if raw_path.startswith(("/", "\\")):
        raise ValueError("absolute paths are outside a contributor package")

    parts: list[str] = []
    for part in raw_path.replace("\\", "/").split("/"):
        if part in {"", "."}:
            continue
        parts.append(part)
    return Path(*parts) if parts else None


def page_dependencies(page: Page) -> tuple[tuple[Path, ...], tuple[str, ...]]:
    """Read literal local resource paths from a supplied HTML page."""

    parser = HTMLDependencyParser()
    try:
        source_html = page.source.read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        raise BuildError(
            f"Cannot read {page.source.relative_to(ROOT)} as UTF-8 HTML."
        ) from error
    parser.feed(source_html)
    parser.close()

    dependencies: list[Path] = []
    invalid_references: list[str] = []
    seen_dependencies: set[Path] = set()
    seen_invalid_references: set[str] = set()

    for reference in parser.references:
        try:
            dependency = local_dependency_path(reference)
        except ValueError:
            if reference not in seen_invalid_references:
                invalid_references.append(reference)
                seen_invalid_references.add(reference)
            continue
        if dependency is None:
            continue

        source_path = (page.source.parent / dependency).resolve()
        if not source_path.is_relative_to(MODULES_ROOT):
            if reference not in seen_invalid_references:
                invalid_references.append(reference)
                seen_invalid_references.add(reference)
            continue

        if dependency not in seen_dependencies:
            dependencies.append(dependency)
            seen_dependencies.add(dependency)

    return tuple(dependencies), tuple(invalid_references)


def package_files_by_name(page: Page) -> dict[str, tuple[Path, ...]]:
    """Index exact candidate filenames within one supplied page package."""

    candidates: dict[str, list[Path]] = {}
    package_root = page.source.parent.resolve()
    for candidate in page.source.parent.rglob("*"):
        if (
            not candidate.is_file()
            or candidate == page.source
            or not candidate.resolve().is_relative_to(package_root)
        ):
            continue
        candidates.setdefault(candidate.name, []).append(candidate)

    return {
        name: tuple(sorted(paths, key=lambda path: path.as_posix()))
        for name, paths in candidates.items()
    }


def cannot_resolve_report(
    page: Page, required_path: str, candidates: tuple[Path, ...]
) -> str:
    """Format the requested report for missing or ambiguous candidates."""

    lines = [
        "Cannot resolve:",
        f"required path: {required_path}",
        f"candidate files: {'none' if not candidates else 'multiple'}",
    ]
    if len(candidates) > 1:
        lines.extend(
            f"- {candidate.relative_to(page.source.parent).as_posix()}"
            for candidate in candidates
        )
    lines.append(f"page: {page.source.relative_to(ROOT).as_posix()}")
    return "\n".join(lines)


def intake_page(page: Page) -> tuple[PageIntake, tuple[str, ...]]:
    """Plan deterministic file copies to the paths explicitly required by HTML."""

    dependencies, invalid_references = page_dependencies(page)
    candidates_by_name = package_files_by_name(page)
    asset_moves: list[AssetMove] = []
    errors = [
        cannot_resolve_report(page, reference, ())
        for reference in invalid_references
    ]

    for required_path in dependencies:
        supplied_path = (page.source.parent / required_path).resolve()
        if supplied_path.is_file():
            continue

        if ".." in required_path.parts:
            errors.append(cannot_resolve_report(page, required_path.as_posix(), ()))
            continue

        candidates = candidates_by_name.get(required_path.name, ())
        if len(candidates) == 1:
            asset_moves.append(
                AssetMove(source=candidates[0], destination=required_path)
            )
            continue

        errors.append(cannot_resolve_report(page, required_path.as_posix(), candidates))

    return PageIntake(asset_moves=tuple(asset_moves)), tuple(errors)


def intake_pages(pages: dict[str, Page]) -> dict[str, PageIntake]:
    """Validate every package before the build changes the output directory."""

    intakes: dict[str, PageIntake] = {}
    errors: list[str] = []
    for page in pages.values():
        intake, page_errors = intake_page(page)
        intakes[page.name] = intake
        errors.extend(page_errors)

    if errors:
        raise BuildError("\n\n".join(errors))
    return intakes


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


def copy_intake_assets(page: Page, output_directory: Path, intake: PageIntake) -> None:
    """Copy validated candidate files to HTML's explicit required destinations."""

    for move in intake.asset_moves:
        destination = output_directory / move.destination
        if destination.exists():
            raise BuildError(
                f"Asset intake destination already exists: {destination}"
            )
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(move.source, destination)
        print(
            "\n".join(
                [
                    "Automatic unique structural match → resolve",
                    "Automatically moved assets to:",
                    f"required path: {move.destination.as_posix()}",
                    f"candidate file: {move.source.relative_to(page.source.parent).as_posix()}",
                    f"page: {page.source.relative_to(ROOT).as_posix()}",
                ]
            )
        )


def render_page(page: Page, output: Path, intake: PageIntake) -> None:
    """Publish a contributor's already-rendered HTML page.

    Contributors upload finished HTML; this only copies it (and whatever
    sits alongside it, such as an assets/ folder) into the built site.
    """
    output_directory = output / "modules" / page.output_directory
    copy_page_support_files(page, output_directory)
    copy_intake_assets(page, output_directory, intake)
    shutil.copy2(page.source, output_directory / "index.html")


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
    <p>Made with ❤️ by <a href="https://github.com/shreyasmeher" target="_blank" rel="noopener noreferrer">Shreyas Meher</a> and <a href="https://github.com/xingyuanzhao-project" target="_blank" rel="noopener noreferrer">Xingyuan Zhao</a></p>
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
    validate_path_prefixes(headings)
    pages = discover_pages(headings)
    resolved = resolve_headings(headings, pages)
    intakes = intake_pages(pages)

    clean_output(output)
    copy_static_site(output)
    copy_module_static_files(output, pages)
    for page in pages.values():
        render_page(page, output, intakes[page.name])
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
