# Phase 0 Kickoff — AICTE Integrated Institution Complaint Monitoring (SIH26264)

Produced 2026-10-28, per Section 17 of `AICTE_CASE_MONITOR_MASTER_PROMPT_v3.md`.
**No application code has been written.** This is the kickoff deliverable only:
architecture summary, repo layout, ADR list, tokens spec, component gallery
screen list, CI job list, and risks — waiting for approval before Phase 0
execution (tokens package, contrast script, component gallery, CI skeleton,
Valkey Streams test, styled sign-in screen) begins.

This repository previously held an unrelated prior build (APAAR, SIH26263).
Per `docs/decision-log.md`, that build's domain code, secrets, and session
artifacts have been removed; only the generic infra *shapes* Appendix B names
as reusable remain, pending rewrite and re-testing against this product.

---

## (a) Architecture summary

Modular monolith + one worker, five containers behind Caddy, per Section 10.
No Kubernetes/Kafka/microservices — the workload is bounded (officers, not
the public) and correctness/auditability matter more than horizontal scale.

```
                                 ┌─────────────────────────┐
                                 │        Browser /         │
                                 │  Expo app (iOS/Android)  │
                                 └─────────────┬─────────────┘
                                               │ HTTPS (TLS, HSTS, CSP)
                                               │ WS/SSE (realtime)
                                 ┌─────────────▼─────────────┐
                                 │   Caddy (proxy)           │
                                 │   TLS, security headers,  │
                                 │   serves SPA + /api/v1    │
                                 └──────┬───────────┬────────┘
                                        │           │
                         ┌──────────────▼──┐   ┌────▼─────────────┐
                         │   api (FastAPI)  │   │  WS gateway       │
                         │  12-step request │   │  (ticket-auth'd,  │
                         │  pipeline        │   │  per-channel authz│
                         │  (Sec. 10)       │   │  + SSE fallback)  │
                         └──────┬───────┬───┘   └────────┬──────────┘
                                │       │                │
                    RLS session │       │ outbox row     │ subscribe
                    (SET LOCAL  │       ▼                │ (Last-Event-ID
                     app.*)     │  ┌─────────────┐       │  resume)
                                │  │ outbox_events│──────┘
                                │  └──────┬──────┘
                                │         │ relay worker
                     ┌──────────▼───┐     ▼
                     │ PostgreSQL 18 │  ┌────────────┐
                     │ RLS, pg_trgm, │  │  Valkey     │
                     │ monthly       │  │ Streams +   │
                     │ partitions    │  │ pub/sub     │
                     │ (case_events) │  └─────┬──────┘
                     └───────┬───────┘        │
                             │                │ fan-out
                     ┌───────▼────────────────▼───────┐
                     │  worker (ARQ):                  │
                     │  outbox relay · SLA scanner ·    │
                     │  alert dispatcher · overlap      │
                     │  evaluator · report runner ·     │
                     │  import runner · nightly jobs     │
                     │  (projection replay, counter      │
                     │  reconciliation, integrity,       │
                     │  audit-head anchor, key rotation) │
                     └───────────────────────────────────┘
```

**Request pipeline (every endpoint, Section 10):** request ID → auth →
session/step-up check → rate limit → input validation → `authz.can()` →
begin transaction with RLS context → business logic → event + projection +
counters + outbox + audit row, one transaction → commit → response →
post-commit publish by relay.

**Event sourcing core:** `case_events` is append-only (DB trigger rejects
UPDATE/DELETE); `cases` is a deterministically rebuildable projection
(`scripts/rebuild_projection.py`); a nightly job diffs projection vs. replay
and alerts on drift (`PROJECTION_DRIFT`). No code path writes `cases.status`
directly — this is the mechanism that makes R7/R8 testable by reconciliation
rather than by trust.

**Overlap engine (Section 8) and SLA engine (Section 7) are pure libraries**
in `rules/`, consumed by the worker's overlap evaluator and SLA scanner —
kept separate from FastAPI so they can be property-tested and mutation-tested
in isolation (Section 13).

---

## (b) Repo layout

Current state after cleanup, target state for Phase 0 exit:

```
.
├── apps/
│   ├── web/              # Vite + React 19 SPA (TanStack Router/Query) — EMPTY, rebuild
│   └── mobile/            # Expo SDK 58 app — EMPTY, rebuild in Phase 7
├── packages/
│   ├── ui-tokens/         # Section 9.2 tokens, icon map, contrast script — NEEDS REBUILD
│   ├── ui-web/            # NOT YET CREATED — web component library (glass + solid cards)
│   ├── ui-native/         # NOT YET CREATED — RN component library (Liquid Glass / Material 3)
│   ├── api-client/        # generated TS client from OpenAPI — regenerate once backend exists
│   └── i18n/              # en/hi/ta ICU scaffolding — kept, needs AICTE string keys
├── backend/
│   └── app/
│       ├── core/          # security.py, db.py (RLS helper), config.py, redis.py, deps.py — kept, revise
│       ├── authz/         # policy.py (can() shape) — kept, revise for the 10 AICTE roles
│       ├── realtime/      # outbox.py, relay.py, tickets.py, channels.py — kept, revise channel names
│       ├── adapters/      # base.py (LIVE/SANDBOX/NOT_CONFIGURED/UNAVAILABLE) — kept, add AICTE adapters
│       ├── routers/       # audit, auth, data_rights, integrations, integrity, realtime, uploads — kept, revise
│       └── models.py      # REMOVED — AICTE domain model (Section 6.1) built fresh in Phase 2/3
├── rules/
│   └── rules/             # engine.py, types.py, registry.py — kept (pure-function shape)
│                           # catalog/ REMOVED — AICTE overlap + SLA rules built fresh in Phase 4/5
├── infra/
│   ├── docker-compose.yml # REPIN: postgres:16→18, redis:7→valkey (Section 15 open item 11)
│   ├── Caddyfile           # add TLS/HSTS/CSP (Appendix A defect #5)
│   └── scripts/            # backup.sh, restore.sh — kept, revise role names
├── scripts/
│   ├── check-data-origin.sh    # kept, generic — Section 1.3 guard
│   └── check-icon-imports.sh   # kept, rename @apaar/* → new scope
└── docs/
    ├── decision-log.md    # this cleanup + ADR tracking (new)
    ├── phase0-kickoff.md  # this file
    ├── metrics.md         # NOT YET CREATED (Section 6.5)
    ├── design-contrast.md # NOT YET CREATED (generated by contrast script)
    └── ui-evidence/       # NOT YET CREATED, phase-N screenshot packs
```

**Open item:** `packages/validation/` previously held APAAR ID-format
validation and is now empty; propose folding business-day/ID-format pure
functions into `rules/` rather than recreating a separate package (ADR
needed — low-stakes, default unless objected to).

**Package scope rename:** everything currently importable as `@apaar/*`
(ui-tokens, i18n, api-client) needs a new scope. Proposing `@icm/*` to match
`icm-platform` — pending approval before Phase 0 execution touches these
files.

---

## (c) ADR list — Section 15 open items and verification method

| # | Open item | Blocks | Verification method |
|---|---|---|---|
| 1 | Official Bureau/Cell + Regional Office list (AICTE page vs. Wikipedia disagree) | M13 seed data | Admin-editable, versioned master seeded from `aicte.gov.in/bureaus` with `source_url`; open a request to AICTE to confirm. Never hard-code a single list as truth. |
| 2 | Nature-of-complaint taxonomy / SLA for non-CPGRAMS case types | M3 categories, SLA engine | Seed only the verified PGRC "matter type" list (Section 6.1) as top level; sub-categories entered by AICTE PGRC/RB via admin console, labelled "suggestions only" until confirmed. |
| 3 | CPGRAMS export format / API access | `CpgramsFeed` adapter | Ship `NOT_CONFIGURED` + CSV/XLSX import with a saved mapping profile; ask AICTE's Nodal PG Officer directly for a sample export. |
| 4 | AICTE Permanent ID exact format | Institution resolution (Stage 0) | Configurable regex, default `^1-\d{6,12}$` from the two public examples; never reject unknown formats silently — route to `INSTITUTION_UNRESOLVED`. |
| 5 | Complaint mailbox integration feasibility | `MailIntake` adapter | Ship `NOT_CONFIGURED` interface only; ask AICTE IT. |
| 6 | Retention schedule for case records | M15 privacy | Configurable, default unset (no auto-deletion) until AICTE records a policy; flagged `UNVERIFIED` in Admin. |
| 7 | NIC SSO desired | Auth | Adapter interface defined, `NOT_CONFIGURED`; ask AICTE IT during pilot planning. |
| 8 | DPDP exemption status for AICTE as State instrumentality | Privacy posture | Design as if NOT exempted (Section 7.4); revisit with legal input, do not assume exemption. |
| 9 | Multilingual embedding model (candidate `intfloat/multilingual-e5-small`) Hindi/Tamil quality + licence | Overlap engine text-similarity signal | Run `scripts/eval_overlap.py`-style spot check against real (or pilot) Hindi/Tamil complaint text before adopting; fallback is trigram similarity, which ships first regardless. |
| 10 | ARQ maintenance status | Worker job queue choice | Check PyPI release cadence/issue activity on install day; record verdict here before committing; Dramatiq is the fallback. |
| 11 | Valkey Streams/pub-sub parity (no official confirmation found) | M10 realtime fabric | **Phase 0 blocking test**: a script that does XADD + XREADGROUP + PUBLISH/SUBSCRIBE against the pinned Valkey image and asserts correctness before the outbox relay is built on top of it. If it fails, fall back to a Redis-compatible image and log that substitution here. |
| 12 | TypeScript 7 toolchain compatibility | Web build | Try `typescript@7.0.2` against Vite 8 + the rest of the pinned stack on install day; pin back to latest 6.x and log it if anything breaks. |
| 13 | Hindi/Tamil native review | i18n strings | All hi/ta strings marked "machine-reasoned, needs native review" in this log until a native reviewer signs off; never presented as final to end users before that. |
| 14 | Boundary dataset for region maps | Region-wise dashboard visuals | Default to tile-grid cartogram / ranked bars (Section 9.6); only switch to a real boundary map if AICTE supplies an official dataset, recorded here with its source. |
| 15 | Package/workspace scope rename (`@apaar/*` → `@icm/*`) | All TS packages | Proposed default `@icm/*`; confirm before Phase 0 execution renames imports across `packages/` and `apps/`. |

None of these are resolved by guessing; each gets a dated entry in
`docs/decision-log.md` when actually checked.

---

## (d) Tokens package spec (`packages/ui-tokens`)

Single source of truth, generated to CSS variables, Tailwind `@theme`,
React Native theme objects, and the Android Material colour scheme. **No raw
hex outside this package** — enforced by a lint rule in the CI job list below.

**Values to encode exactly as measured in Section 9.2** of the master
prompt: `canvas` gradient (light/dark), `surface-0/1/2`, `outline`, `ink`,
`ink-muted`, `brand-50`…`brand-700`, `grad-deco`, `grad-text`, `focus`, and
the seven status-palette pairs (`pending`, `under_process`, `disposed`,
`transferred`, `escalated`, `overdue`, `overlap`) in both light and dark,
each already verified ≥4.5:1 (text) / ≥3:1 (non-text) in the source table —
the contrast script re-verifies these on render, not just on the token
values, because glass/scrim compositing can change effective contrast.

**Typography:** Urbanist or Plus Jakarta Sans (choice logged after an eyeball
comparison against `ui-refrence-iamge.png` in Phase 0 execution) with Noto
Sans Devanagari / Noto Sans Tamil fallbacks; scale 12/14/16/18/20/24/32/40;
weights 400/500/600/700; tabular numerals.

**Shape/spacing/elevation/motion:** card 24 / tile 18 / input 14 / button 16
(pill on mobile primary actions) / chip-nav 999; 4-pt grid, gutters
16/24/32; one soft shadow family (`0 8px 24px rgba(10,46,69,.12)` and
`0 2px 8px rgba(10,46,69,.08)`); 180–280ms ease-out, spring (damping 18,
stiffness 220) for nav pill/sheets, honouring reduce-motion.

**Icon map (`icons.ts`):** full replacement of the current APAAR-era file.
Must cover 100% of the required semantic set in Section 9.9 (dashboard,
cases, institution, alert, overlap/link, transfer, escalate, dispose,
pending, under-process, overdue, remark, document, timeline, search, filter,
report, export, region, bureau, officer, settings, security, language,
help, sign-out, refresh, live-connection — plus any used beyond this list),
each mapped to an SF Symbol and a Material Symbol name, validated against
the installed symbol sets at build time (script fails on an unknown name).

**Contrast script plan (`scripts/check-contrast.*` → `docs/design-contrast.md`):**
1. Enumerate every declared text/background token pair and every status
   pair (light + dark).
2. Compute relative luminance → contrast ratio per WCAG 2.x formula.
3. Fail with a non-zero exit (and fail CI) on any text pair <4.5:1 or
   non-text/UI-component pair <3:1.
4. Write the full pair-by-pair table to `docs/design-contrast.md` so a
   human reviewer can see the margin, not just a pass/fail.
5. Phase-6-era follow-up (not Phase 0): re-run contrast checks against
   actual rendered screenshots where glass/scrim compositing is involved,
   since token-level contrast doesn't capture `backdrop-filter` effects.

---

## (e) Component gallery screen list (`/dev/gallery` or Storybook)

Each in light and dark, each state where applicable (default, hover/focus,
disabled, loading, error):

1. Shell (sidebar rail + command bar, collapsed/expanded)
2. Buttons (primary/secondary/destructive/ghost, pill and rect)
3. Inputs (text, select, date range, search-with-icon)
4. Chips (filter row: default, active/outlined-active)
5. Cards (institution card, solid content card)
6. Tiles (dashboard stat tile, workload row tile)
7. Gauge (semi-circular SLA compliance gauge with ticks)
8. Bar chart (one highlighted gradient bar + marker dot, inactive bars `brand-50`)
9. Table (dense case list: sticky header, status badge column, keyset pager)
10. Status badge (all seven statuses × icon × label, light/dark)
11. Pill navigation (web sidebar active item, mobile floating bottom nav with expanding active pill)
12. Glass surfaces (command bar, floating filter bar, dialog/sheet) with the
    `@supports not (backdrop-filter)` / reduced-transparency fallback shown side by side

Gate for Phase 0: this gallery screenshotted and reviewed against
`ui-refrence-iamge.png` for palette/radii/gradient/nav/chart-style fidelity
(Section 9.11 point 5), before any product screen is built.

---

## (f) CI job list (GitHub Actions)

- `lint` — ESLint/Prettier (web, mobile), Ruff (backend, rules)
- `typecheck` — tsc across all TS packages/apps, mypy or pyright for backend
- `unit` — Vitest (web/packages), pytest (backend/rules), `hypothesis` property tests on business-day engine + overlap scorer
- `integration` — real Postgres 18 + Valkey services; RLS cross-bureau/cross-region leak tests; T1/T2/T3 visibility tests; outbox atomicity (kill worker mid-transaction); resume-after-disconnect; counter reconciliation; projection replay equality
- `valkey-streams-test` — Phase 0 blocking test for ADR item 11 (XADD/XREADGROUP/PUBLISH against the pinned image)
- `web-e2e` — Playwright per role
- `visual-snapshots` — Playwright screenshots at 1440×900 / 1024×768 / 390×844, light+dark, diffed against baselines
- `axe` — zero serious/critical violations
- `lighthouse` — accessibility ≥95 on dashboard + cases pages, performance ≥90
- `mobile-typecheck` — `tsc` + `expo-doctor` + `npx expo install --fix --check`
- `maestro` — mobile flows where runners allow
- `contrast-check` — the script from (d), fails CI below 4.5:1/3:1
- `icon-guard` — `scripts/check-icon-imports.sh`, bans non-approved icon libraries/emoji-as-icon
- `data-origin-guard` — `scripts/check-data-origin.sh`, bans fixture generators outside `tests/` and hand-inserted business data in migrations
- `gitleaks`, `semgrep`, `bandit`, `pip-audit`, `npm-audit`, `trivy`, `syft-sbom` — supply chain
- `zap-baseline` — against the composed stack
- `mutmut` (or equivalent) — mutation testing on SLA engine + overlap scorer (scheduled, not every PR)

All jobs must actually run green on GitHub, not only locally, before any
phase gate is marked passed (Appendix A process-failure lesson).

---

## (g) Risks

1. **Valkey Streams/pub-sub parity unconfirmed** — mitigated by the Phase 0
   blocking test (ADR 11); fallback to Redis-compatible image if it fails.
2. **Bureau/Cell and Regional Office master data disputed between sources**
   — mitigated by admin-editable, versioned, provenance-tagged master data;
   never presented as AICTE-authoritative until confirmed.
3. **CPGRAMS has no public API** — mitigated by `NOT_CONFIGURED` adapter +
   CSV/XLSX import path; real integration depends on AICTE's Nodal PG
   Officer providing an export format.
4. **No real case data until a pilot or AICTE import exists** — the product
   must look correct and honest with zero cases (empty states), which is a
   harder UI bar than seeding fake rows; tested explicitly per screen.
5. **Multilingual embedding model quality on Hindi/Tamil complaint text is
   unverified** — overlap engine ships with trigram fallback regardless, so
   this risk affects signal quality, not correctness of the gate it's
   checked against.
6. **TypeScript 7 / Vite 8 / Tailwind 4 toolchain is very new** (versions
   verified 28 Oct 2026) — risk of churn; ADR 12 covers the fallback.
7. **Carrying forward infra files that were wrong in the prior build**
   (`postgres:16`, `redis:7`, `apaar_owner` superuser) — tracked explicitly
   in the repo layout section (b) as "kept for revision, not reuse-as-is";
   must be repinned/rescoped before Phase 1, not silently carried.
8. **GIGW 3.0's 88 checkpoints and DPDP Rules 2025 commencement dates** are
   from secondary sources — compliance claims must cite the primary source
   once checked, not the secondary summary used here.
9. **Scope rename (`@apaar/*` → `@icm/*`) touches every TS package import**
   — mechanical but repo-wide; doing it once, early, before more code is
   written on top of the old scope, rather than mid-phase.

---

**Waiting for approval before Phase 0 execution** (tokens package values
committed, contrast script written, component gallery built, CI skeleton
added, Valkey Streams test run, login screen styled) begins, per Section 17.
