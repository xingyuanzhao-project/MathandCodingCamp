# EPPS Math Coding Bootcamp

This repository builds the camp website from contributor page folders and the
manager's navigation map.

Published site: [EPPS Math Coding Bootcamp](https://xingyuanzhao-project.github.io/MathandCodingCamp/).
Modules page: [EPPS Math Coding Bootcamp Modules](https://xingyuanzhao-project.github.io/MathandCodingCamp/modules/).

## Repository layout

```text
settings/
  site-map.yml               # manager's displayed navigation hierarchy
src/
  static/                    # site shell, shared assets, existing redirect pages, downloads
  pages/                     # contributor page folders
scripts/
  build_site.py              # builds the website
_site/                       # generated website; do not edit or commit
```

`_site/` is build output. Edit its source files instead.

## For contributors

Create one self-contained page folder below `src/pages/modules/`. For example:

```text
src/pages/modules/math/day-6/example/
  example.qmd
  assets/
    chart.png
```

Each page folder has one entry file:

- `A.html` is copied into the generated website;
- `B.qmd` is rendered by Quarto;
- `C.Rmd` is rendered by Quarto.

Keep images, CSS, JavaScript, data, and page-specific libraries with that
page, normally under `assets/`. Use a filename that is unique below
`src/pages/`, because the manager map refers to the contributor file by name.

## For the manager

Edit `settings/site-map.yml`. Its order and nesting become the modules page.
Any heading can contain nested headings or a list of items. The existing
structure includes days and sessions, data downloads, group presentations,
feedback, and resources; it can grow with new headings or nested headings.

Items use one of these forms:

```yaml
Day 6:
  Night Session:
    - Example lesson: "example.qmd"

Data Files for Download:
  - Example data: "example.csv"

Feedback:
  - Existing form: "https://example.org/form"

Day 7:
  Closing Session:
    - Closing remarks
```

The displayed label is on the left. The value on the right is either:

- a contributor page file (`.html`, `.qmd`, or `.Rmd`);
- a static file stored under `src/static/`, including downloadable files;
- an existing `https:` or `mailto:` URL.

A plain list item is displayed as text without a link.

The build distinguishes pages and files from the target itself, not from the
heading containing it:

- `.html`, `.qmd`, and `.Rmd` targets are discovered under `src/pages/`;
- other filenames are discovered under `src/static/` and linked as files;
- `https:` and `mailto:` values remain external links.

## Build

Run:

```sh
python3 scripts/build_site.py
```

Python 3 is required. Pages using QMD or RMD also require
[Quarto](https://quarto.org/). The command writes the generated website to
`_site/`. Pushing to `main` runs the same build in GitHub Actions and publishes
that output to GitHub Pages.
