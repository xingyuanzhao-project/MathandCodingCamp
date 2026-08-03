# EPPS Math Coding Bootcamp

This repository builds the camp website from contributor page folders and the
manager's navigation map.

Published site: [EPPS Math Coding Bootcamp](https://xingyuanzhao-project.github.io/MathandCodingCamp/).
Modules page: [EPPS Math Coding Bootcamp Modules](https://xingyuanzhao-project.github.io/MathandCodingCamp/modules/).

## Repository layout

```text
settings/
  site-map.yml               # manager's displayed navigation hierarchy
modules/                     # page folders, downloads, presentations
static/                      # site shell and shared site assets
scripts/
  build_site.py              # builds the website
_site/                       # generated website; do not edit or commit
```

`_site/` is build output. Edit its source files instead.

## For contributors

Create one self-contained page folder below `modules/`. For example:

```text
modules/math/day-6/example/
  example.html
  assets/
    chart.png
```

Render your page to a single `.html` file yourself (with Quarto or
otherwise) and commit that file. The build only copies pre-rendered HTML;
it does not run Quarto and will not render a `.qmd` or `.Rmd` source.

Keep images, CSS, JavaScript, data, and page-specific libraries with that
page, normally under `assets/`. The build copies everything else in your
page's folder alongside the `.html` file, so a self-contained `assets/`
folder travels with it automatically. The manager map refers to your page
by its full path from the repository root, so the filename itself no
longer needs to be unique across `modules/`.

## For the manager

Edit `settings/site-map.yml`. Its order and nesting become the modules page.
Any heading can contain nested headings or a list of items. The existing
structure includes days and sessions, data downloads, group presentations,
feedback, and resources; it can grow with new headings or nested headings.

Items use one of these forms:

```yaml
Day 6: modules/math/day-6
  Night Session:
    - Example lesson: "modules/math/day-6/example/example.html"

Data Files for Download:
  - Example data: "modules/downloads/example.csv"

Feedback:
  - Existing form: "https://example.org/form"

Day 7:
  Closing Session:
    - Closing remarks
```

The displayed label is on the left. The value on the right is either:

- a page or static file's exact path, relative to the repository root
  (for example `modules/math/day-6/example/example.html`);
- an existing `https:` or `mailto:` URL.

A plain list item with no colon is displayed as text without a link.

Every local path is resolved exactly as written: `build_site.py` fails the
build if the named path does not exist. There is no filename search and no
fallback, so a typo is caught immediately instead of silently producing a
dead link.

A heading may optionally carry a path prefix after its colon, the way
`Day 6:` does above. When present, every item nested under that heading —
including through further nested headings — must resolve to a path under
that prefix, or the build fails. The prefix is a validation constraint
only; it is never shown to visitors, who still see just the label before
the colon. Headings with no folder of their own, such as `Night Session`,
simply omit the prefix and stay display-only.

Page targets must end in `.html` and live under `modules/`; the build does
not render `.qmd` or `.Rmd`, so a contributor's page must already be
rendered to HTML (see "For contributors" above). Other local targets, such
as downloads, can live under `modules/` or `static/` and are linked as
plain files instead of pages.

## Build

Run:

```sh
python3 scripts/build_site.py
```

Only Python 3's standard library is required; the script does not call
Quarto itself. ([Quarto](https://quarto.org/) is what contributors use
locally to produce the `.html` they commit — see "For contributors" above.)
The command writes the generated website to `_site/`. Pushing to `main`
runs the same build in GitHub Actions and publishes that output to GitHub
Pages.
