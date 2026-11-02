# abs-census

Python scripts in this project must be run using the project-local virtual
environment at `.venv`, not system Python.

- Windows: `.venv\Scripts\python scripts\<script>.py`
- Before running anything, make sure dependencies are installed:
  `.venv\Scripts\python -m pip install -r requirements.txt`

## Fixing a failing check

If a check fails and the fix would change how a value is calculated or
defined, stop and show the proposed change before applying it. Definitions
change only through an ADR amendment.

## Current status

Phase 6 (web app) is complete -- see [ADR-005](docs/decisions/ADR-005-web-app.md).

## Web app

Run from `web/`:

- `npm ci` -- install exactly the locked versions (`package-lock.json`)
- `npm test` -- Vitest
- `npm run lint` -- ESLint
- `npm run build` -- production build (`web/dist/`)
- `npm run dev` -- local dev server

`VITE_BASE_PATH` sets the sub-path for a GitHub Pages build, e.g.
`VITE_BASE_PATH=/abs-census/ npm run build`.

## ADR dates

- The **Date** of an ADR, and of each amendment, is the day it is first committed to Git.
  Use today's real date from the system clock (run `date` or `git log -1 --date=short`).
  Never estimate or guess a date.
- Check with: `git log --format="%ad %h %s" --date=short -- docs/decisions/`
- Dates in ADR-002 (Amendment 1), ADR-003, ADR-004 and ADR-005 were corrected on
  2026-11-01 to follow this rule.
