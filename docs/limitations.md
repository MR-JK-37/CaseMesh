# Known limitations

Honest, current-state limitations after Phase 4 execution — updated every
phase per the Definition of Done (Section 0 rule 9). Not a TODO list; what's
actually true right now.

## This deployment shows TEST DATA, not real AICTE data

User decision (Section 1.4(b), docs/decision-log.md Phase 2): the institution
registry contains only synthetic sandbox rows, clearly labelled as such via
`source_name` and a permanent red banner on every screen. Nothing in this
system should be presented to anyone as real AICTE data. Switching to real
data requires a real, authorised source (Section 1.2) and flipping
`settings.tenant_mode`, not silently removing the banner.

## Overlap and SLA alerting exists; M9's reports module doesn't

Phase 4 built Section 8's institution resolution, pair scoring, the
event-driven trigger, the grouped queue, confirm/dismiss, coordination
threads/messages/decisions, and `scripts/eval_overlap.py`. Phase 5
built M8's alert catalogue (`raise_alert()`, dedup-once-per-threshold,
`OVERLAP_DETECTED`/`OVERLAP_HIGH_CONFIDENCE`/`SLA_POLICY_MISSING`/
`SLA_APPROACHING`/`SLA_BREACHED`/`CASE_STALE`/`TRANSFER_UNACCEPTED`/
`ESCALATION_RAISED`/`IMPORT_COMPLETED`/`PROJECTION_DRIFT`/
`COUNTER_DRIFT`) and the real-time fabric that delivers them (R13).
M9's reports module (bureau-wise, region-wise, institution-wise
history, pending ageing, disposal rate, monthly/quarterly performance)
is still unbuilt. `can()`'s permission matrix now covers Phase 1-5
actions (adds `alert:list`/`alert:ack` to Phase 1-4's set) — still not
the full "every endpoint" matrix Section 4.2 asks for long-term,
because report endpoints don't exist yet. `tests/test_authz_matrix.py`
iterates exactly the actions that exist, honestly.

## Overlap scoring omits "same complainant" and "same documents" signals

Section 8.3's signal table lists an HMAC blind index on complainant
email/phone and a SHA-256 match on attachments. Phase 3 never captured
complainant identity at registration and no document-upload feature
exists — inventing those fields just to light up a signal would be the
exact kind of fabrication Section 0 rule 2 forbids, and adding real
complainant-identity capture is also a step Section 0 says to stop and
ask about first ("loading personal data about real people"), not
something to fold into a scoring-engine phase unannounced. `rules/rules/
overlap.py`'s docstring documents this explicitly; the five other
signals (different bureau, category compatibility, shared reference,
text similarity, time proximity) are real and tested.

## Institution resolution (Section 8.1) has no live caller yet

`rules/rules/overlap.py#resolve_institution` is built and unit-tested
(exact Permanent ID match, blocked-and-scored fuzzy match, refuses to
guess when ambiguous) but nothing in the live app calls it — Phase 3's
case registration uses a structured institution picker (no free-text
institution name to resolve), and neither a bulk case-import flow nor a
CPGRAMS feed exist yet to supply one. Ready for whichever of those is
built first; gate-tested per Section 16's Phase 4 requirement, not
wired to an endpoint.

## Overlap recomputation is synchronous, not event-queued

Section 8.4 calls this "event-driven" in the sense of "reacts to a case
event"; there is no async job worker in this codebase (Section 10's ARQ
workers are unbuilt). `app/services/overlap.py#recompute_overlap_for_
institution` runs inline, in the same request/transaction, every time
any event is appended to any case — correct and real-time, but it means
every case-action request pays the cost of rescoring that institution's
other cases before the HTTP response returns. Fine at this prototype's
volume; would need a queue if one institution ever accumulated hundreds
of concurrently-open cases.

## Coordination threads are scoped to one overlap pair, not a whole institution

Section 8.5 describes grouping by institution ("one `overlap_group` per
institution") and also describes thread/decision actions without
pinning them to a specific pair vs. the whole group. This build keeps
the institution-level grouping for the *queue's display* but scopes
each coordination thread to one specific `OverlapCandidate` pair — the
same two-case shape `case_events`' RLS policy already uses, which kept
the access-control model consistent with Phase 3 rather than inventing
a new one. An institution with three overlapping cases gets up to three
separate pairwise threads, not one combined conversation.

## `scripts/eval_overlap.py` currently reports on test-fixture labels, not real officer decisions

The script is real and correct (precision/recall from confirmed vs.
dismissed candidates, "uncalibrated" with zero labels) — but the only
confirm/dismiss decisions in the dev database right now came from this
session's own test suite and manual verification, not real officers
triaging real overlaps. `docs/overlap-eval.md`'s current numbers are
demonstration output, not a real evaluation; the small-sample warning
it prints makes this explicit rather than hiding it.

## Confidential (T3) case tier is not implemented

Section 4.3 describes three visibility tiers; Phase 3 implements T1
(`cases`, broad metadata, no RLS) and T2 (`case_events`, RLS-restricted
to handling bureau + competent_authority + system + self-authored). The
`Case.confidential` flag exists on the model and is always set to
`false` by the current registration screen, but nothing in the backend
yet changes visibility behavior for a confidential case — T3's stricter
access rules (Section 4.1: confidential-case export requires
competent_authority approval) are unbuilt.

## Case registration UI supports one institution per case, not several

`CaseInstitutionLink` and the register endpoint support multiple
institutions per case (an array in the request body), matching the data
model's design for cases that genuinely span institutions. The
registration screen only lets an officer pick one institution at a
time — a UI gap, not a data-model one.

## Disposal type is a fixed UI list, not a validated server-side enum

`CaseDetailPage`'s dispose form offers "Resolved / Not substantiated /
Referred elsewhere" as options, but `app/routers/cases.py`'s dispose
endpoint accepts any string for `disposal_type` — the server doesn't
reject an unlisted value sent directly to the API.

## `POST /users` rejects RFC 2606 reserved-TLD emails (`.local`, `.test`, `.example`)

This is the live, validated behavior of the Admin Users creation
endpoint (`EmailStr` via `email-validator`), found while setting up a
real `bureau_head` account for Phase 3 browser verification — a
reasonable control, not loosened (see `docs/decision-log.md` 2026-10-29
entry #3 for the full reasoning). The practical effect: `admin@icm.local`
(the exact convention `scripts/seed_dev.py`'s own bootstrap admin uses)
and any `@example.test` address cannot be created through the live
Admin Users screen — only via direct DB insertion, which is how
`scripts/seed_dev.py` and the pytest fixtures both work around it. An
admin hitting this gets a generic "Could not create user (duplicate
email, weak password, or not permitted)" message with no indication
it's specifically the email domain.

## Institution alias matching exists as logic, not as a wired feature

`institution_aliases` has storage + a minimal add/list endpoint
(`institution:alias_manage`, super_admin only). Phase 4's
`resolve_institution` can score free text against institution names but
does not yet also check `institution_aliases` as additional match
candidates, and (see above) nothing calls it live yet either. Section
8.1's "each confirmation adds an alias, so the system improves from
real decisions" feedback loop is not built — there is no live resolution
flow to confirm anything into.

## Institution versioning is basic, not full history

Section 5/M2 asks for institutions to be "admin-editable and versioned."
Re-importing updates fields in place (visible as a diff in the import
preview, and the owning `import_job_id` changes) but there is no
`institution_versions` table or point-in-time history view — only "what
changed in this import" is visible, not "every change ever."

## Mobile app is unbuilt

`apps/mobile` has no screens. `pnpm turbo run typecheck` passes for it
(manifest/dependency correctness only). Mobile visual QA has not been
performed — Phase 7.

## Twelve real web screens exist

Sign-in, `/home` (now the real Command Dashboard, Section 9.6 — Phase 6),
`/security`, `/admin/users`, `/institutions`, `/institutions/:id`,
`/import`, `/cases`, `/cases/:id`, `/cases/register`, `/overlap`,
`/alerts`, `/reports`. Section 9.7's full screen list (Workload board
with drag-and-drop reassignment, split-view case detail, global
Ctrl/Cmd+K command palette, Admin console beyond users) still doesn't
exist. The web shell (`Shell.tsx`) is a minimal top nav, not the
sidebar-rail + glass command-bar shell Section 9.7 describes — deferred
until there are enough real screens to justify it.

## Dashboard tiles are computed live, not from a `dashboard_counters` cache table

Section 6.5 describes `dashboard_counters` as incrementally updated in
the same transaction as every state change, with heavy aggregates from
materialized views refreshed on a schedule. Phase 6 instead recomputes
every tile from raw rows on every `GET /dashboard/tiles` call
(`app/services/dashboard.py`) — correct and impossible to let drift at
this project's data volume (a few thousand rows), but it means every
dashboard load does a full scan of open cases to compute SLA status,
ageing buckets and workload. This would need the cache-table approach
before it could serve real AICTE-scale traffic or a large concurrent
officer count; not attempted this phase because building it correctly
means touching every existing case-mutation call site (register,
assign, remark, transfer, escalate, dispose, reopen — roughly ten
places across `app/routers/cases.py`/`overlap.py`) to keep the cache
atomic with the state change, a large enough change to warrant its own
phase rather than being folded into Phase 6's scope.

## Report catalogue has four reports, not the full Section 9.7 list

Built: bureau/cell-wise workload, status-wise summary, pending ageing,
monthly disposal rate. Not built: region-wise, institution-wise
complaint history, overlapping/duplicate-case reports, transfer and
escalation flow, and quarterly performance — plus Section 9.7's
scheduled/recurring report runs (`report_runs` as a background job) and
per-report parameter forms beyond an optional `bureau_id` filter on the
workload report. Every report's SQL hash (Section 9.7: "exports...
the SQL hash") is not computed — only a SHA-256 of the exported data,
which proves integrity but not which query produced it; the distinction
is documented in `app/services/csv_export.py`'s module docstring.

## Saved views have no sharing

`GET/POST/DELETE /views` (Section 9.7) is personal-only: a saved
filter set is visible and deletable only by the user who created it.
There is no "share with my bureau" or "team default view" mechanism,
and the frontend doesn't yet have UI to save or apply a view from
`CasesListPage.tsx` — the API exists and is tested
(`tests/test_dashboard_and_reports.py`), but nothing in the UI calls it
yet.

## `GET /cases`'s two "simplified" metrics differ from Section 6.5's exact wording

Documented in full in `docs/metrics.md`'s "Known simplifications"
section: "transferred (count in period)" is approximated as "cases
currently in `transferred` status" rather than a true latest-transfer-
in-period window query, and disposal rate uses
`disposed/received` rather than `disposed/(open_at_start + received)`
because there's no "open at start of period" snapshot. Both are honest,
simpler numbers — not fabricated ones — flagged here and in
`docs/metrics.md` rather than silently matching the spec's wording
without matching its behavior.

## The real-time toast has no reconnect-with-backoff loop

`useRealtimeToast.ts` opens one `EventSource` per mount and never
retries on close/error — Section 6.4(b)'s jittered exponential backoff
reconnect is unbuilt. A dropped connection (network blip, server
restart) silently stops delivering live updates until the next full
page navigation remounts the hook. The WebSocket gateway
(`app/routers/realtime.py`) has the same gap on the client side that
would consume it, though none exists yet — only the SSE path is wired
into the UI.

## SLA scanning and escalation are standalone scripts, not scheduled jobs

`scripts/scan_sla.py` (SLA approaching/breached, stale cases,
unaccepted transfers, counter drift) and `scripts/seed_holidays.py`
are run manually or by an external cron, not by an in-app scheduler —
Section 10's worker infrastructure (ARQ or equivalent) is unbuilt, see
the ADR item below. The escalation ladder itself is a single
`ESCALATION_RAISED` alert on manual escalate, not a timed multi-rung
ladder with per-rung delays.

## Only in-app real-time delivers alerts; email/push do not

`NotificationProviders` (Section 3) remains `NOT_CONFIGURED` — every
alert in Phase 5 reaches a user only via the WS/SSE toast and the
`/alerts` page, never email or push, even though the alert rows and
catalogue are real. This is an honest gap, not a silent failure: the
Integrations Console (a later phase) is where this status should
become visible in the UI itself.

## i18n is English-only

No Hindi/Tamil strings anywhere, including every screen built so far.
Section 9.10's en/hi/ta-from-day-one requirement is not yet met; it needs
to be before any screen is considered truly done, not deferred
indefinitely.

## Rate limiting is fixed-window, not sliding-window

`_check_rate_limit` in `routers/auth.py` uses Valkey INCR+EXPIRE, a
simpler fixed window. Section 7.4 asks for a sliding window; honest
simplification, not the stronger guarantee.

## TOTP self-enrollment has a real gap for mid-session role changes

New users get TOTP pre-provisioned at creation time if their role requires
it. A user later *promoted* into a TOTP-required role via a role change
has no enrollment flow triggered automatically. Role-change support
doesn't exist yet at all (no endpoint), so this is latent, not yet
reachable.

## Backend/e2e coverage gaps

- No committed Playwright spec drives the real login→import→verify flow,
  the Phase 3 register→assign→remark→escalate→dispose→reopen flow, or
  the Phase 4 register→overlap-banner→confirm/coordinate→decide flow,
  end to end — all three were verified manually with scripted TOTP-code
  generation and screenshots (`docs/ui-evidence/phase-1/`,
  `docs/ui-evidence/phase-2/`, `docs/ui-evidence/phase-3/`,
  `docs/ui-evidence/phase-4/`), but that script isn't checked in as a
  test, because `scripts/seed_dev.py`
  generates a random password/TOTP secret on every run with no
  deterministic test-mode override yet. `apps/web/e2e/phase0-axe.spec.ts`
  only covers the unauthenticated sign-in shell and the dev gallery.
- `login_attempts` cleanup in tests is unscoped (`DELETE FROM
  login_attempts`), harmless in an ephemeral CI database, sloppy in a
  shared one.
- The import test suite leaves orphaned `import_jobs`/`source_documents`
  rows for the one error-row test case (no institution is ever created to
  anchor cleanup to); harmless dev-DB clutter, not a correctness issue.
- Any case, user, bureau, or institution row ever referenced by a
  `case_events` row is permanently undeletable by design (the append-only
  trigger blocks cascaded deletes too) — the Phase 3 pytest suite's
  fixtures are never cleaned up for this reason, so the dev/CI database
  accumulates rows across runs. Harmless (RLS still scopes visibility
  correctly regardless of row count), but worth knowing before querying
  the dev DB directly and being surprised by volume.
- The login rate limiter (`_check_rate_limit`, Valkey INCR+EXPIRE) uses
  one bucket per source IP, and every `TestClient` instance in the test
  suite shares the same test-harness IP — this intermittently 429'd
  unrelated logins across a full-suite run (Phase 4/5 sessions both hit
  it). Resolved in Phase 5 by moving the bucket reset into
  `tests/conftest.py` as a single autouse fixture that runs after every
  test regardless of file, instead of each file needing its own copy —
  5/5 consecutive full-suite runs clean after the fix.

## CI has not run on GitHub

`.github/workflows/ci.yml` was updated through Phase 2 but this repository
still has no remote and no commits. Nothing in this file has actually run
on GitHub Actions yet.

## Material Symbols loads from Google Fonts, not self-hosted

Unchanged from Phase 0 — Section 9.9 asks for a self-hosted subset.

## No TLS in local dev

Unchanged from Phase 0 — Caddy serves `:80` with security headers but no
certificate until Phase 9's real deployment.
