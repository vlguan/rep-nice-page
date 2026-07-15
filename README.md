# rep-nice-page

Public catalog of replica fashion items trending on r/FashionReps, enriched from Weidian (translated, photos), with one-click Superbuy handoff. Dead Weidian listings are removed automatically by daily revalidation.

## Layout

- `web/` — Next.js catalog site
- `scraper/` — Python daily pipeline (discover → judge → enrich → revalidate)
- `docs/superpowers/` — spec + implementation plan

## Railway setup (3 services, one project)

1. **Postgres** — add the Railway Postgres plugin. Copy `DATABASE_URL`.
2. **web** — service from this repo, root directory `web/`.
   - Env: `DATABASE_URL`, `SUPERBUY_PARTNER_CODE` (affiliate code appended to
     Superbuy handoff links; new-user registrations via those links are
     attributed to our affiliate account. Omit to disable.)
   - Build/start: Railway autodetects Next.js (`npm run build` / `npm start`).
3. **scraper** — service from this repo, root directory `scraper/` (Dockerfile detected).
   - Env: `DATABASE_URL`, `ANTHROPIC_API_KEY`, `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`
   - Settings → Cron Schedule: `0 9 * * 0` (weekly, Sundays 09:00 UTC). Restart policy: Never.

Reddit credentials: Reddit blocks unauthenticated JSON access, so the scraper uses the
official OAuth API (application-only grant, read-only). Create an app at
https://www.reddit.com/prefs/apps (type: **script**, any name, redirect uri
`http://localhost:8080`) and use its client id + secret. Locally these can live in
`scraper/.env` (gitignored), which the CLI loads automatically.

Apply migrations once (and after schema changes):

    cd web && DATABASE_URL=<railway url> npx drizzle-kit migrate

## Local development

    docker run -d --name repnice-test-pg -e POSTGRES_PASSWORD=test -p 5433:5432 postgres:16
    cd web && DATABASE_URL=postgresql://postgres:test@localhost:5433/postgres npx drizzle-kit migrate

- Web: `cd web && DATABASE_URL=postgresql://postgres:test@localhost:5433/postgres npm run dev`
- Scraper tests: `cd scraper && TEST_DATABASE_URL=postgresql://postgres:test@localhost:5433/postgres .venv/bin/python -m pytest`
- Web tests: `cd web && TEST_DATABASE_URL=postgresql://postgres:test@localhost:5433/postgres npx vitest run`
- Pipeline smoke run (5 posts, real network + LLM):
  `cd scraper && DATABASE_URL=postgresql://postgres:test@localhost:5433/postgres ANTHROPIC_API_KEY=sk-... .venv/bin/python -m scraper.run --limit 5`

## Ops

- Did last night's run work? `SELECT * FROM scrape_runs ORDER BY id DESC LIMIT 5;`
- An item wrongly deactivated revives automatically next run if its listing is live again.
