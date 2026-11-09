# AGENTS.md — working conventions for Riskmatris Live

## Language

- **English for all developer-facing text**: code, comments, log messages, commit messages, PRs, issues, CI config.
- **UI text is localized**, never hardcoded: add keys to BOTH `static/i18n/sv.json` (reference) and `static/i18n/en.json` and keep them in parity. Use `t("key", {param})` from `static/js/i18n.js` for dynamic strings, `data-i18n*` attributes for static HTML. The server sends error *codes* (see `riskmatris/i18n.py`); the client translates via `server.*` keys. CSV export takes `?lang=sv|en`.

## Tooling gotchas

- **Verify edits**: the edit tool can report success but silently drop hunks. After every edit batch, confirm with `grep`/`git diff` that the change is actually in the file before committing.
- Approval prompts can block chained commands — split them.
- After deploys, hard-reload (Ctrl+Shift+R): static assets are cached (content-hash cache busting covers `.js`/`.css`/`.json`).

## Security (write secure code by default)

- Rate-limit public endpoints per real client IP (trust proxy headers only from the known proxy network). Session codes are capabilities: 8 chars, and read endpoints are rate-limited too.
- WebSocket: check `Origin` against Host, one-time tickets for admin auth, per-IP/total connection caps, per-connection message rate limit, never put tokens in URLs.
- Always `secrets.compare_digest` for tokens; sanitize all user text on input (`sanitize_user_text`) and escape on output; parameterized SQL only; escape CSV cells against formula injection (`sanitize_csv_cell`).
- Ship security headers (CSP, nosniff, Referrer-Policy, X-Frame-Options); generic error messages to clients, details in logs; API docs off in production (`RISKMATRIS_ENABLE_DOCS=0` default).
- Pin dependencies and the Docker base image by digest; `pip-audit` runs in CI; Dependabot is configured.

## Accessibility (WCAG 2.1 AA by default)

- Text contrast ≥ 4.5:1 in both themes; visible focus indicator (outline + ring) on all interactive elements; skip link; single `<main>`; logical heading order.
- All interactive elements keyboard-operable (real buttons, Enter/Space, tabindex+role only when needed); icon-only buttons need accessible names; dialogs get `role="dialog"`, focus moved in on open, Tab trapped, focus restored on close, Escape closes.
- `aria-live` on dynamic status (counts, errors); progress bars get `role="progressbar"` + aria values; forms need labels.
- Verify with axe/Lighthouse (or similar) on all views in both themes, plus a keyboard-only walkthrough. IBM-style heuristics produce false positives (favicon links, icon buttons) — document those instead of redesigning.

## Process

- Run `pytest -q`, `ruff check .`, `ruff format --check .` before committing — CI runs the same.
- Small fixes go straight to `master`; features/fixes with scope go on `feature/<name>` + PR with `Closes #N`.
- Releases: annotated tag `vX.Y.Z` (`git tag -a`), push the tag, create a GitHub release from it. Minor per feature batch, patch for fixes.
- Test on the test instance (separate container via `RISKMATRIS_CONTAINER_NAME`) before tagging.
- Commit messages in English, imperative mood; generated-by trailer is added by the tooling.
