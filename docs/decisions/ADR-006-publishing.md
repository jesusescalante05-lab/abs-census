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

### Gate 2: ABS attribution

Pending.

## Deployment

Pending.
