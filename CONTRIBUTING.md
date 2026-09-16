# Contributing

## Language

- **English:** code, comments you add from now on, commit messages, pull request titles and
  descriptions, and repository documentation.
- **Hebrew is fine:** GitHub issues and task discussion, and everything the customer sees in
  the product.

## Commits and pull requests

- Commit under **your own name and the email verified on your GitHub account**
  (`git config user.name` / `git config user.email`). Check before your first commit on a new
  machine.
- **No AI attribution lines** — no `Co-Authored-By` trailers for AI tools and no
  "Generated with …" footers. Contributors are the people on the team.
- Commit messages: a short imperative subject, then a body that says *why*, not only what.
- Pull request descriptions: what changed, why, how it was verified (tests, browser, data).
- Do not use `@mentions` in issues or PRs unless you really need to notify someone — every
  mention emails them. Write names in plain text.

## Merging

- A PR merges when the **engine** and **frontend** checks are green. The Cloudflare Workers
  check belongs to the marketing site and does not gate the engine.
- Mark work that must not merge yet as a **draft** and say why in the description.
- Do not rebase, force-push or un-draft someone else's branch without asking them.
- Never force-push `main`.

## Tests that guard the product

Run them before opening a PR (from `apps/shaked-engine/backend`):

```bash
.venv/bin/python -m pytest -q                    # the full suite
.venv/bin/python scripts/check_surfaces.py        # screen = PDF = Excel on every parcel
.venv/bin/python tests/mutations.py "$(pwd)/.venv/bin/python"   # the tests fail when the code breaks
```

and from `apps/shaked-engine/frontend`:

```bash
npx tsc --noEmit
```

CI runs all of them, plus a full seed and a sellability check.

## Data

Read [`POC/layer_a/data/DATA_LAW.md`](POC/layer_a/data/DATA_LAW.md) before touching any
source. In short: never sweep the municipal archive, stop at any CAPTCHA, never store
applicant names, delete permit drawings after extraction, and do not scrape commercial sites.

## Ownership

One file, one owner at a time. Two places everyone touches need a heads-up in the team
channel first: `backend/alembic/versions/` (migrations) and `requirements.txt`.
