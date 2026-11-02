# ADR-006: Publishing

**Product:** Perth Housing Stress Explorer
**Status:** Proposed
**Date:** 2026-11-02
**Phase:** 7 (Publish to GitHub Pages)
**Depends on:** ADR-004 (web data packaging), ADR-005 (web app)

## Context

Publishing to GitHub Pages. ADR-005 Limitation 7 set two gates before publishing: review the
`npm audit` advisories, and check the ABS attribution text.

## Publishing gate

### Gate 1: npm audit (Decision: Accepted)

- `npm audit` reports 6 moderate advisories. They are one advisory in `minimatch` (<11.0.1,
  denial of service via glob patterns), reported through 6 packages in the ESLint chain:
  `minimatch`, `@eslint/config-array`, `eslint`, `@eslint-community/eslint-utils`, `@eslint/js`,
  `eslint-plugin-react-refresh`.
- `npm audit --omit=dev` reports 0 vulnerabilities: nothing reaches the published app (`web/dist`).
- Not reachable: ESLint reads glob patterns only from the project's own config.
- Worst case: `npm run lint` slows down on the developer's machine.
- `npm audit fix --force` rejected: it would downgrade `@eslint/js` 10.0.1 to 9.39.5 (breaking).
- Review again when a new ESLint release updates `minimatch`.

### Gate 2: ABS attribution (Decision: Accepted)

- Checked on 2026-11-02 against the ABS conditions of sale (Creative Commons attribution
  section): https://www.abs.gov.au/about/legislation-and-policy/purchasing-data/abs-conditions-sale
- ABS rule: "Source: ABS" is for unchanged material; "Based on ABS data" is for modified or
  derived material, and the licence terms must be made clear.
- This product is derived (indicator, hotspots, simplified and masked boundaries), so:
  "Source:" changed to "Based on"; added "© Commonwealth of Australia" and the CC BY 4.0
  licence URL; the disclaimer now names the author's own analysis; removed the
  "(Verify this wording ...)" placeholder.
- The text is defined once, in ABS_ATTRIBUTION in scripts/export_web.py.
- check_export_web.py now checks that abs_attribution starts with "Based on", contains
  "CC BY 4.0" and the licence URL, and has no "verify this wording" placeholder.
- Re-export result: only run_metadata.json changed; both PMTiles files, sa2_points.geojson
  and sa2_details.json were byte-identical, so the export is reproducible.

## Deployment

- Host: GitHub Pages, project site https://jesusescalante05-lab.github.io/abs-census/
  (repo jesusescalante05-lab/abs-census, branch master). Pages source: "GitHub Actions".
- Node: web/.nvmrc pins 24.16.0 (same as the local machine); the workflow reads it.
- One workflow, .github/workflows/deploy.yml. Triggers: push to master, pull_request,
  workflow_dispatch.
  - Job build: npm ci, npm run lint, npm test, npm audit --omit=dev, then npm run build with
    VITE_BASE_PATH=/abs-census/, then upload web/dist as the Pages artifact.
  - Job deploy: only on master (not on pull requests); needs build; publishes the artifact.
  - Permissions: contents read, pages write, id-token write. Concurrency group "pages",
    cancel-in-progress false.
  - Every action is pinned to a full commit SHA, with its version as a comment
    (same rule as the exact npm versions in ADR-005).
- Pre-publish secrets check (2026-11-02): the full Git history contains only .env.example with
  the placeholder PGPASSWORD=changeme. The real .env is ignored by .gitignore (line 2) and was
  never committed. The commit author email is public by choice.
- Licence: a LICENSE file with the MIT licence for the code, with a note that the data in
  web/public/data/ is based on ABS data under CC BY 4.0 (see Gate 2).
- About page: no change. It is React state only and changes no URL, so a page refresh
  cannot produce a 404.
- After the first deploy: repeat the ADR-005 browser checklist on the live URL, plus:
  .pmtiles requests return HTTP 206, and the About page shows the new ABS attribution.

## Limitations

- The export checks (check_export_web.py) do not run in CI, because the script connects to
  PostgreSQL first. Data files change only through the local export, which runs the full
  check (ADR-004). Planned later: an --offline mode for the file-only checks.
