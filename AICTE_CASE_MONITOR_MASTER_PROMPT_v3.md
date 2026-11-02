# MASTER BUILD PROMPT v3: Integrated Institution Complaint Monitoring and Status Dashboard (AICTE, SIH26264)

> HOW TO USE: Paste everything below the line into your build AI (Claude Code etc.) as the first message, and attach (1) the problem-statement text, (2) the reference image `ui-refrence-iamge.png`. For agents with limited context, paste Sections 0 to 8 once, then paste ONE phase kickoff from Section 16 at a time. Section 9 (UI) is self-contained and is also valid for any other app you build with the same look.
> v3 changes vs v2: new problem statement (SIH26264); a **UI-first rule set** written because the previous build shipped unstyled HTML (Appendix A lists every defect found in it); a design system extracted from your reference image with verified contrast; an explainable overlap-detection engine; a visibility model that lets bureaus see who else is handling an institution without exposing complaint content.

---

## 0. ROLE AND OPERATING RULES

You are a principal engineer, product designer, security architect and DevOps lead building a production-grade, real-time, multi-role platform with a web app and a mobile app, on a free-of-cost stack.

Hard rules:
1. **Never invent facts, data, API behaviour, endpoints, versions, policies or free-tier limits.** If something is not in Section 15 (verified) or you have not checked it on the official source today, mark it `UNVERIFIED` and record how you will verify it in `docs/decision-log.md`.
2. **No fake data inside the product.** The product never seeds, generates or displays synthetic institutions, complaints, officers, counts, timelines or "AI findings". Section 1 defines what real data is allowed and where it comes from. An integration that is not configured returns `NOT_CONFIGURED`; it never returns a fabricated or "simulated" success.
3. **UI is a deliverable, not a later phase.** No screen may be committed as plain unstyled HTML. Every phase gate in Section 16 requires screenshots (light and dark, three viewport widths for web; device or simulator screenshots for mobile) stored in `docs/ui-evidence/phase-N/`. A phase whose limitations file contains "unstyled", "placeholder UI" or "design not started" **fails its gate**. The design tokens package (Section 9) is built in Phase 0, before any screen.
4. **Humans decide.** The system never closes, transfers, merges or penalises anything on its own. Rules and models raise **suggestions with reasons**; an authorised officer accepts, edits or dismisses each one, and the action is audited.
5. **Never claim** approval or endorsement by AICTE, MoE, DARPG, NIC or any government body. Show "Prototype for SIH 2026" in the footer and About page until a real owner adopts it.
6. **Stop and ask the human before:** adding any paid service; loading personal data about real people; sending any request to a government production system; scraping any site; changing a role's permissions; weakening a security control; marking a verified fact `UNVERIFIED` away.
7. Work in phases; do not start a phase until the previous gate passes. Every acceptance criterion gets an automated test. Report per phase: built / test results / UI evidence / open issues / decisions logged. No step-by-step recaps.
8. **Pin and verify versions.** Section 15 lists versions checked on 28 Oct 2026. Install exactly those lines (`npx expo install --fix` for Expo packages), run `npx expo-doctor`, and fail the phase on any peer-dependency mismatch. (The previous build pinned `expo-router ~6.0.0` against Expo SDK 58, a mismatch.)
9. **Definition of Done for any feature:** code + tests + styled UI in all states (loading, empty, error, partial, offline, no-permission) + English/Hindi/Tamil strings + accessibility check + audit event + realtime event (where relevant) + docs line + limitations entry if anything is partial. "Works in the API" is not done.

---

## 1. DATA POLICY (real data only, lawfully sourced)

### 1.1 What "real" can and cannot mean
- **Real complaint data is confidential administrative data of AICTE. It does not exist in any public API and must not be scraped, bought, reconstructed or invented.** Cases enter the platform only by (a) authorised AICTE users registering a case, (b) authorised bulk import of AICTE's own existing registers (CSV/XLSX), or (c) later, a sanctioned feed from CPGRAMS or AICTE's mail system (Section 3, `NOT_CONFIGURED` until AICTE grants access). The system starts with **zero cases** and shows honest empty states.
- **Real reference data is allowed and required** for everything public: institutions, AICTE Permanent IDs, states/regions, Bureau/Cell names, national timelines.

### 1.2 Data classes and allowed sources

| Class | Examples | Allowed source | Rule |
|---|---|---|---|
| Public reference | AICTE-approved institution names, Permanent IDs, address, state, district, programmes, approved intake | AICTE Extension-of-Approval (EoA) reports and mandatory-disclosure documents published by institutions; AICTE public notices; data.gov.in resources that exist | Import with full provenance (1.3); human-validate before activation. **Do not automate against `facilities.aicte-india.org`: its robots rules disallow automated fetching (checked 28 Oct 2026).** Ask AICTE for a data-sharing arrangement. |
| Organisation master | Bureaus/Cells, Regional Offices, officer designations | AICTE website (bureaus page, regional-offices document) | Seed from official pages with `source_url`; **editable by `super_admin` with versioning**, because sources disagree (Section 15). |
| Policy reference | Grievance timelines: 21 days standard, 3 days priority, 48 hours to forward a misrouted grievance, 30 days for appeals | DARPG OM dated 23.08.2024 (verified) | Seed as the default **CPGRAMS-source** SLA policy with citation. AICTE-internal case types get **no default SLA** until AICTE sets one (Section 7.2). |
| Operational | Cases, parties, documents, actions, transfers, overlaps, alerts | Authorised users, authorised imports | Real, encrypted, audited. Starts empty. |
| Derived | counters, ageing, overlap suggestions, reports | Computed by the platform | Always traceable to rows, rule versions and the metric definition (Section 6.5). |
| Test fixtures | synthetic rows for automated tests | Generated inside `tests/` only | Ephemeral CI databases only. Never imported by application code. |

### 1.3 Provenance (anti-fake mechanism, mandatory)
Every row not typed by a user carries `data_origin` (`public_import` | `provider_fetch` | `user_entered` | `derived`), `source_name`, `source_url`, `retrieved_at`, `source_checksum`, `import_job_id`, `verified_by`, `verified_at`. The UI shows "Source: <name>, retrieved <date>" wherever such data appears. CI fails the build if application code imports the fixture generator or if a non-test migration inserts business data.

### 1.4 Honest limits (put them in the docs and the pitch)
- Public EoA PDFs are per institution and parsing can be wrong; every import is human-validated and diffed against the previous year.
- The institution master will be incomplete until AICTE shares its register. **Institution resolution never guesses silently** (Section 8).
- Overlap-detection quality cannot be claimed before officers label real pairs. Until then the UI labels confidence "uncalibrated" and the docs say so. No accuracy percentage may appear anywhere unless it is computed from labelled real pairs by `scripts/eval_overlap.py`.
- For the SIH demo use **one of**: (a) a pilot with AICTE staff or consenting volunteers entering real, non-sensitive test cases; or (b) a physically separate **TEST sandbox tenant** (own database, own subdomain, permanent red "TEST DATA, NOT REAL" banner on every screen and export). Never mix (b) into the real tenant. State which one is being shown.

---

## 2. PRODUCT CONTEXT (from the problem statement, verbatim intent)

- **Problem:** AICTE, SIH26264, Software / Smart Automation, Regulation Bureau. Complaints about technical institutions reach different Bureaus/Cells (Regulation Bureau, Public Grievance Redressal Cell and others). There is no central real-time view, so actions overlap, disposal is delayed, and nobody can tell which Bureau/Cell is dealing with an institution.
- **Objective:** a single-window dashboard where authorised officials: see all institution-related cases; identify the handling Bureau/Cell; track full status and movement; spot RB/PGRC overlap; avoid duplicate action; monitor pending/disposed/under-process/transferred/escalated cases; generate institution-wise, region-wise, Bureau/Cell-wise and status-wise reports; receive alerts for pending and near-deadline cases.
- **Target users:** Regulation Bureau, PGRC, other Bureaus/Cells, Regional Offices/Centres, authorised officers and senior management, Competent Authority.
- **Innovation expected:** data matching, rules and/or AI-assisted analytics that identify complaints about the same institution even when descriptions or references differ, and display **"Potential Overlapping Cases – Coordination Required"**.
- **Outcome:** one source of truth; less duplication; no conflicting parallel actions; better coordination; timely disposal; accountability and transparency; real-time management view; data-driven decisions.

### 2.1 Traceability matrix (every line of the statement maps to a test)

| ID | Problem-statement requirement | Module | Acceptance test (automated) |
|---|---|---|---|
| R1 | Unique Institution ID / AICTE Permanent ID, name, address, region, details | M2 | Institution profile renders all fields with provenance; Permanent ID unique and format-validated |
| R2 | Consolidated history of complaints/cases per institution | M2, M3 | Institution page lists every case across all bureaus the viewer may see, ordered by date, with counts by status |
| R3 | Unique Case ID, date of receipt, nature/category, status, assigned Bureau/Cell, assigned officer, last action, next action required, date of last action, expected disposal date | M3 | Case creation rejects any missing mandatory field; all ten fields visible on list and detail |
| R4 | Auto-identify complaints on the same institution handled by RB, PGRC or others, even if text/reference differs | M5 | Pair with different wording and different reference numbers but same institution is flagged; pair on different institutions is not |
| R5 | Overlap alert to authorised officials | M5, M8 | Alert reaches both handling bureaus' heads and assigned officers within the realtime target |
| R6 | Link/map related cases | M5 | Officer links two cases with a relationship type; both show the link; unlink is audited |
| R7 | Dashboard: total, pending, under process, disposed, transferred, beyond timeline, institution-wise status, bureau-wise workload | M6 | Each tile equals a recomputation from raw rows (reconciliation test) and updates live after an action |
| R8 | Complete chronological history, responsible officer/bureau, date-time stamp, remarks, documents, transfer/escalation history | M4 | Timeline is append-only; every state change creates exactly one event; edit/delete of an event is impossible via API and DB role |
| R9 | Search/filter by institution name, Permanent ID, case ID, bureau/cell, region, category, status, date range | M7 | Property-based test: result set equals the SQL filter on the same predicates; p95 latency target met |
| R10 | Alerts: duplicate/overlap, pending reminders, escalation, timeline/SLA | M8 | Time-travel test (fake clock in tests only) fires each alert exactly once at each threshold |
| R11 | Reports: bureau-wise, region-wise, institution-wise history, pending ageing, disposal rate, overlaps, monthly/quarterly performance | M9 | Report totals equal dashboard totals for the same filters; export opens in Excel without formula execution |
| R12 | Avoid duplication and ensure coordination between bureaus | M5 | Coordination thread + lead-bureau decision recorded; "proceed in parallel" requires a reason |
| R13 | Real time | M10 | Action in one session appears on another officer's open dashboard within the latency target; reconnect resumes without gaps |
| R14 | Web and mobile for all target users | M11, M12 | Role matrix (Section 4) passes on both clients; visual evidence pack complete |

---

## 3. REAL INTEGRATIONS (adapter layer with honest states)

Every external system sits behind an interface with providers and a status. **Allowed statuses: `LIVE`, `SANDBOX`, `NOT_CONFIGURED`, `UNAVAILABLE`.** The Integrations Console shows them. No provider ever returns invented data.

| Adapter | Real system | Reality (verified 28 Oct 2026) | Build |
|---|---|---|---|
| `AicteReferenceImporter` | AICTE EoA reports, mandatory-disclosure documents, public notices | Documents are public; the facilities dashboard disallows automated access; data.gov.in AICTE resources found are aggregate tables and one states "The API for this resource does not exist" | PDF/table parsing (`pdfplumber`, Camelot), human review, provenance. Polite rate limit and identifying user-agent. |
| `CpgramsFeed` | CPGRAMS (DARPG) | PIB (Aug 2026) describes CPGRAMS routing, categories, timelines and a planned "NextGen CPGRAMS" with omni-channel intake and automated escalation. **No public API description was found.** | Define the interface (`fetch_new_grievances(since)`), ship `NOT_CONFIGURED`. Provide a **CSV/XLSX import** mapped by a saved column-mapping profile (format `UNVERIFIED` until a real export is seen). Ask AICTE's Nodal PG Officer for the export format or API. |
| `MailIntake` | AICTE complaint mailbox | Not assumed to exist | IMAP/Graph adapter interface, `NOT_CONFIGURED`. Manual registration from letters/emails always works. |
| `NotificationProviders` | SMTP/Brevo (email), Expo Push (FCM/APNs) | Free tiers: verify limits on the day | Real sends only; sandbox mode writes to a dev mailbox and says so in the UI. SMS: `NOT_CONFIGURED` (needs a government SMS gateway). |
| `OgdIndiaClient` | data.gov.in | Many resources have no API | Cache + provenance; file import fallback. |
| `HolidayCalendar` | Public holiday data | Python `holidays` package (India) provides national and state holidays | Used for business-day SLA maths; `super_admin` can add AICTE-specific closures with a source note. |
| Aadhaar, paid vendor APIs | not used | | Never built. The platform processes no Aadhaar numbers. |

Complaint categories are **not** invented here: Section 6.1 explains the initial taxonomy and its `UNVERIFIED` status.

---

## 4. ROLES, LOGINS AND ACCESS CONTROL (RBAC + scope + visibility tiers)

### 4.1 Roles (10)

| # | Role | Who | Scope | Core permissions |
|---|---|---|---|---|
| 1 | `super_admin` | Platform administrator (AICTE IT) | System | Users, roles, Bureau/Cell master, SLA policies, categories, holidays, integrations, imports, config. **No access to case content** by default (break-glass with two-person approval, audited). |
| 2 | `competent_authority` | Chairman / Vice-Chairman / Member Secretary / designated authority | All | Read everything, final decision on escalations and overlap disputes, approve exports of confidential cases, all reports. |
| 3 | `senior_management` | Advisers and senior officials | All (aggregates + coordination metadata; content per 4.3) | Dashboards, reports, overlap queue, comment on escalations. |
| 4 | `bureau_head` | Head of a Bureau or Cell (RB, PGRC, others) | Own Bureau/Cell (full content); others (coordination metadata) | Assign/reassign within bureau, accept or reject incoming transfers, record overlap decisions, escalate, approve disposal where policy requires, see bureau workload. |
| 5 | `case_officer` | Officer in RB/PGRC/other bureau | Cases assigned to them or their bureau queue | Act on cases: remark, request information, attach documents, transfer (to bureau), escalate, propose disposal. |
| 6 | `regional_officer` | Regional Office/Centre staff | Institutions in their region | Read cases for region's institutions (content per 4.3), add field remarks/inspection notes, receive region alerts. |
| 7 | `nodal_pg_officer` | AICTE's Nodal PG Officer (DARPG role) | All grievance-source cases | Monitor pendency, review categorisation, route misrouted grievances, monthly review pack. |
| 8 | `registry_operator` | Dak/intake clerk | Intake queue | Register cases from letters/emails, bulk import, attach documents. **Cannot decide, transfer or dispose.** |
| 9 | `auditor` | Internal audit / vigilance reviewer | All (no complainant identity) | Read-only audit log, integrity checks, analytics. |
| 10 | `system` | Workers, importers | n/a | Machine identity; no interactive login. |

All interactive roles authenticate with email + password (Argon2id) and **TOTP is mandatory for roles 1 to 4, 7 and 9, recommended for others**. Step-up re-authentication (fresh TOTP or biometric on mobile) for: transfer, escalation, disposal, export of confidential data, role change. Lockout default 5 failures / 10 minutes (configurable). Sessions: 15-minute access token, 7-day rotating refresh token with family revocation, device list with remote sign-out. Government SSO (e.g. NIC) is an optional future adapter, `NOT_CONFIGURED`.

### 4.2 Authorisation model
`can(user, action, resource)` in **one** module (`authz/policy.py`), enforced at the API and again in PostgreSQL **Row-Level Security** (`SET LOCAL app.user_id`, `app.role`, `app.bureau_ids`, `app.region_ids` inside each transaction). The matrix below is generated into a test that iterates every (role x endpoint x tier) and fails CI if any endpoint lacks a rule. A deny returns 404 for hidden resources (no existence leak) and 403 for visible-but-forbidden actions; both are audited.

### 4.3 Visibility tiers (the key to "single window" without leaking complaints)

| Tier | Contents | Who sees it |
|---|---|---|
| **T1 Coordination metadata** | case ID, institution, handling Bureau/Cell, assigned officer, top-level category, status, dates (received, last action, due), last-action *type*, overlap and SLA flags | Every authenticated official with `case.view_coordination` (roles 2 to 9 except where T3 applies). This is what lets RB see that PGRC is handling the same institution. |
| **T2 Case content** | description, complainant identity and contact, documents, remarks, internal notes | Handling Bureau/Cell (officers + head), `competent_authority`, region scope for own institutions (read-only), plus any official granted a **time-boxed coordination share** approved by the handling bureau head |
| **T3 Confidential** | cases flagged `confidential` (e.g. vigilance, whistle-blower, safety-of-person matters) | Assigned officer, bureau head, `competent_authority`. Everyone else sees only "A confidential matter exists for this institution; contact the Bureau Head" **and only if they are a bureau head or senior management**; other roles see nothing. |

Complainant identity is encrypted at field level (Section 7.4) and is **never** returned in lists, search results, exports or alerts unless the viewer has T2 and the action is audited.

---

## 5. MODULES

**M1 Authentication and sessions.** Login, TOTP enrolment/recovery, lockout, step-up, device/session list, password change, forced rotation, audit of every event.

**M2 Institution Registry and Profile.** Reference import with provenance (Sections 1.2 and 1.3), alias management, merge-duplicate institutions (two-person), profile page: ID, name, address, state/district, region, programmes/intake where imported, provenance badge, **consolidated case history across all bureaus** (R2), "who is handling now" matrix (bureau x open cases), overlap panel.

**M3 Case Registration and Tracking.** Mandatory fields per R3; multi-institution cases; external references (CPGRAMS registration number, letter/diary number, court case number); source channel; priority; confidentiality flag; document upload; duplicate pre-check on save (shows likely matches before the officer submits); intake queue for `registry_operator`; bulk import with preview, mapping, dry run, chunked/resumable processing, formula-safe error report, rollback window.

**M4 Workflow and Action History.** Append-only event log (Section 6.3); actions: register, assign, reassign, remark, request-information, receive-information, transfer (propose/accept/reject), escalate, link, unlink, propose-disposal, approve-disposal, dispose, reopen. Each event stores actor, bureau/cell, UTC timestamp, remark, attachments, before/after state, request ID. Transfer and escalation history are first-class views.

**M5 Overlap Detection and Coordination.** Section 8.

**M6 Real-time Dashboard.** Tiles and charts from Section 9.6; per-role default view; live counters; drill-down to the exact case list (the tile number must equal the list count).

**M7 Search and Filters.** All eight filters from R9, saved views, shareable URLs, keyboard-first global search (command palette), keyset pagination, exportable result sets.

**M8 Alerts and Notifications.** Section 7.3. In-app inbox, email, push; per-user preferences; acknowledge/snooze (never delete); escalation ladder.

**M9 Reports and Analytics.** Section 9.7 (report catalogue), scheduled monthly/quarterly runs, XLSX/CSV/PDF exports with watermark, hash and parameters footer.

**M10 Real-time Fabric.** Section 6.4.

**M11 Web app.** Section 9.

**M12 Mobile app (iOS + Android).** Section 9.

**M13 Administration.** Users/roles, Bureau/Cell/Regional Office master, categories and sub-categories (versioned), SLA policies (versioned), holiday calendar, escalation ladder, notification templates, saved report definitions, integrations console, import jobs, feature flags.

**M14 Audit, Integrity and Monitoring.** Hash-chained append-only audit log with the chain head anchored outside the database (daily, to a signed file in object storage or Git), nightly integrity job, security alerts, health/ready endpoints, metrics, tracing.

**M15 Privacy and Data Rights.** Complainant notice text, retention schedule (configurable, `UNVERIFIED` until AICTE records policy), correction/erasure workflow that **actually performs the mutation** after two-person approval (the previous build only recorded the decision), export of one's own data.

**M16 Help, Accessibility and About.** Role-based help, accessibility statement, privacy notice, "Prototype" disclaimer.

---

## 6. DOMAIN MODEL, REAL-TIME AND METRICS

### 6.1 Core entities
`institutions`, `institution_aliases`, `regional_offices`, `bureaus` (type `bureau`|`cell`), `users`, `user_assignments` (user to bureau and/or region with role), `cases` (current-state projection), `case_events` (append-only, monthly partitions), `case_institution_links`, `case_parties` (encrypted complainant), `case_documents`, `case_transfers`, `case_links` (duplicate, related, parent/child, appeal-of), `overlap_candidates`, `overlap_groups`, `overlap_decisions`, `coordination_threads`, `coordination_messages`, `coordination_shares` (time-boxed T2 grants), `categories` (versioned), `sla_policies` (versioned), `holidays`, `alert_rules`, `alerts`, `alert_acks`, `notification_prefs`, `device_tokens`, `saved_views`, `report_defs`, `report_runs`, `dashboard_counters`, `source_documents`, `import_jobs`, `audit_log`, `outbox_events`, `idempotency_keys`, `config_versions`.

**Initial category taxonomy (UNVERIFIED, editable, versioned).** The PGRC page states it deals with grievances, complaints and malpractices, including complaints from students, faculty and stakeholders, CPGRAMS grievances, ragging, violations of AICTE norms and standards, VIP and Ministry references, court cases, Parliament questions, RTI matters and miscellaneous. Seed **"matter type"** from that list exactly, and let AICTE's PGRC/RB define the **"nature of complaint"** sub-categories in the admin console (fees and refunds, admission, faculty, infrastructure, approval status, certificates, and so on are suggestions only). Do not present any sub-category list as official.

**Case statuses (from the problem statement):** `pending`, `under_process`, `transferred`, `escalated`, `disposed`. Sub-state fields: `awaiting_information` (boolean), `transfer_state` (`proposed`|`accepted`|`rejected`), `disposal_type` (configurable list). Reopen creates an event and returns to `under_process`. RTI, court and Parliament-question items are matter types with their own configurable SLA, not statuses.

### 6.2 Case ID
Platform ID `ICM-<YYYY>-<6-digit sequence>` allocated by a database sequence (gap-free is not required, uniqueness is). External references live in `external_refs[]` and are searchable.

### 6.3 Event log
`case_events` is append-only (no UPDATE/DELETE grant for the application role; a trigger rejects both). `cases` is the projection, rebuilt deterministically from events by `scripts/rebuild_projection.py`, and a nightly job compares projection to replay (drift = critical alert). Every state change is **one transaction**: event row + projection update + counter updates + outbox row + audit row. No code path updates `cases.status` directly.

### 6.4 Real-time fabric
- **Transactional outbox** to a relay worker to **Valkey** (Streams for durable fan-out, pub/sub for ephemeral presence) to a **WebSocket gateway** (SSE fallback), exactly as in the previous build's design but with the gaps closed: (a) `Last-Event-ID` **resume** so a reconnecting client replays missed events from the outbox; (b) heartbeat every 25 s with client backoff and jitter; (c) one-time WS ticket (30 s, single use) bound to user and IP prefix; (d) **per-channel authorisation at subscribe time and re-checked on role/assignment change**; (e) SSE fallback for proxies that break WebSockets; (f) slow-consumer protection (bounded queues, drop-oldest for presence, never for case events).
- Channels: `user:{id}`, `bureau:{id}`, `region:{id}`, `institution:{id}`, `case:{id}`, `dashboard:{scope}`. Events carry **T1 data only**; clients fetch T2 over REST with their own authorisation.
- **Targets (to be measured, not claimed):** event visible on another officer's screen p95 < 1 s; dashboard tile refresh p95 < 1 s after commit.
- **Valkey vs Redis:** the earlier research did not confirm Streams/pub-sub parity for Valkey from an official page; **write a Phase 0 test** proving XADD/XREADGROUP/PUBLISH on the pinned Valkey image before relying on it, else use Redis-compatible image and log it.

### 6.5 Metrics registry (single definition of every number)
`docs/metrics.md` defines each dashboard metric as SQL, owner, and refresh method; tests assert dashboard = recomputation. Definitions (change only by ADR):
- **Total received** (period): cases with `received_at` in period.
- **Pending**: open cases with status `pending` (not yet acted on by the handling bureau).
- **Under process**: status `under_process` or `escalated` with an action in the last N days (N configurable) shown separately as **Escalated**.
- **Transferred**: cases whose latest transfer event is in the period (count) and, separately, cases currently `transferred` awaiting acceptance.
- **Disposed**: status `disposed` with `disposed_at` in period. **Disposal rate** = disposed in period / (open at start + received in period).
- **Beyond timeline**: open cases with `due_at` < now (business-day aware). **Approaching**: due within the configured warning windows.
- **Ageing buckets**: open cases by business days since receipt, bucket edges configurable.
- **Bureau workload**: open cases per Bureau/Cell and per officer, with overdue share.
Counters are updated **incrementally in the same transaction** and reconciled nightly against full recomputation; drift above zero raises an alert. Heavy report aggregates use materialized views refreshed `CONCURRENTLY` on a schedule, labelled "as of <time>".

---

## 7. SLA, ALERTS, BACKEND RULES

### 7.1 Business-day engine
`due_at` is computed from `received_at` + policy days in **business days** using the holiday calendar (national + configured regional + AICTE closures). The engine is a pure function with property tests (monotonic, weekend-skipping, holiday-skipping, DST-free because IST has no DST).

### 7.2 SLA policies (versioned)
A policy is keyed by `(source, matter_type, priority)` and states `days`, `warn_at[]`, `escalate_after`. **Seed only what is verified:** for `source = CPGRAMS`: standard 21 days, priority 3 days, forward-misrouted within 48 hours, appeals 30 days (DARPG OM 23.08.2024). For every other combination the policy is **absent**: the case shows "SLA policy not set, contact admin" and a `SLA_POLICY_MISSING` alert goes to `super_admin` and the bureau head. Never fill a number by guess. Pausing the clock while "awaiting information" is a policy flag, default **off**, and must be confirmed by AICTE.

### 7.3 Alert catalogue (all configurable, all audited, each fires once per threshold)
`OVERLAP_DETECTED`, `OVERLAP_HIGH_CONFIDENCE`, `INSTITUTION_UNRESOLVED`, `SLA_APPROACHING` (windows from the policy), `SLA_BREACHED`, `PENDING_REMINDER`, `CASE_STALE` (no action for N business days), `TRANSFER_RECEIVED`, `TRANSFER_UNACCEPTED`, `ESCALATION_RAISED`, `ESCALATION_UNATTENDED`, `IMPORT_COMPLETED`, `PROJECTION_DRIFT`, `COUNTER_DRIFT`, `INTEGRITY_MISMATCH`, `SECURITY_*`. **Escalation ladder** (configurable): assigned officer, bureau head, `competent_authority`, with a delay per rung. Channels: in-app (WS), email, push; user preferences honoured except for mandatory security and SLA-breach alerts.

### 7.4 Security controls (condensed; each has a test)
- **Transport/edge:** TLS only, HSTS, strict CSP (no inline script), `X-Content-Type-Options`, `Referrer-Policy`, frame-ancestors none, CORS allow-list, same-site web + API behind one Caddy, cookies `HttpOnly; Secure; SameSite=Lax` plus CSRF token for the web session (the previous build kept tokens in memory and lost login on refresh).
- **Authentication:** Argon2id, TOTP, lockout, rate limits on login, ticket, search and export (Valkey sliding window), step-up, refresh rotation with reuse detection.
- **Data:** AES-256-GCM field encryption with `key_id` and a working **key-rotation job** (rehearsed in a test); HMAC-SHA-256 blind indexes for searchable identifiers (complainant email/phone); record HMAC integrity; encrypted backups.
- **Uploads:** allow-list by magic bytes (PDF, images, DOCX/XLSX/CSV), size caps, random server names, stored outside web root, optional ClamAV container, PDF/Office macro rejection, download via short-lived signed URL with `Content-Disposition: attachment`, per-file SHA-256.
- **Exports:** formula-injection-safe CSV/XLSX; T2/T3 content only with step-up and audit; watermark with user, time, filters.
- **Audit:** hash chain, DB role cannot update/delete, chain head anchored daily outside the database, on-demand verification by `auditor`.
- **Supply chain/CI:** Gitleaks, Semgrep, Bandit, pip-audit, npm audit, Trivy, Syft SBOM (CycloneDX), ZAP baseline against a running stack, pinned lockfiles, Dependabot/Renovate. **A phase cannot pass with an unrun scanner.**
- **Privacy:** DPDP Act and Rules 2025 (notified 13 Nov 2025; commencement phased 14 Nov 2025, 14 Nov 2026, 14 May 2027) apply to complainant personal data: notice, purpose limitation, minimisation, retention schedule, breach-response runbook, grievance route for data principals. Whether AICTE as a State instrumentality is exempted by notification is `UNVERIFIED`: design as if not.

---

## 8. OVERLAP DETECTION ENGINE (the innovation, explainable by design)

**Principle:** deterministic rules first, statistical similarity second, humans last. Every output carries a list of **reasons** an officer can read. No black-box score is shown alone. No LLM is required; an optional local model may *summarise* reasons but never decides.

### 8.1 Stage 0: resolve the institution (never guess silently)
1. If a valid AICTE Permanent ID is present (configurable regex, default `^1-\d{6,12}$`, `UNVERIFIED`: examples seen publicly are `1-` followed by 9 to 10 digits) and exists in the registry: **exact match**.
2. Otherwise normalise the text (lowercase, strip punctuation and honorifics, Unicode NFKC, transliterate Devanagari/Tamil to Latin for matching only, expand abbreviations such as `engg`, `inst`, `tech`, `univ`, remove stop-words such as `the`, `of`), then generate candidates with `pg_trgm` similarity **blocked by state/district/pincode when known**.
3. Score candidates with: trigram similarity, `rapidfuzz` token-set ratio, locality agreement, alias hit. Weights live in config with a version.
4. **Auto-link only if** score >= `T_link` **and** the margin over the runner-up >= `delta`. Otherwise status `INSTITUTION_UNRESOLVED`: the case is saved, **visible**, shown in an "Unresolved institutions" queue, and an officer confirms. Each confirmation adds an alias, so the system improves from real decisions.

### 8.2 Stage 1: candidate cases
For a new or changed case on institution `I`, fetch open cases and cases disposed within the last `W` days on `I` handled by **another bureau/cell** (priority) or by the same bureau under another officer (duplicate risk). Block by institution first: the cost per event is bounded by the number of cases on one institution.

### 8.3 Stage 2: pair signals and score (0 to 100, weights configurable and versioned)
| Signal | How computed |
|---|---|
| Same institution | hard gate (resolved or confirmed) |
| Different handling bureau | boosts priority, shown as "RB and PGRC are both dealing with this institution" |
| Category compatibility | configurable matrix (e.g. approval-related vs fee-related = related) |
| Text similarity | multilingual sentence embeddings (CPU, ONNX via `fastembed`; candidate model `intfloat/multilingual-e5-small`, **verify licence and Hindi/Tamil quality on real text before adopting**) cosine; fallback to trigram on text if the model is unavailable |
| Shared references | regex extraction of letter/diary numbers, CPGRAMS registration numbers, court case numbers from text and fields, exact match |
| Same complainant | HMAC blind index of normalised email/phone (never name alone) |
| Same documents | identical SHA-256 of attachments |
| Time proximity | decay over days |
| Same programme/course | extracted programme mentions matched to the institution's programmes |

Output levels: `INFO` (same institution, different bureau), `POTENTIAL` (score >= `T_potential`), `HIGH` (score >= `T_high` or shared reference/complainant/document). **Thresholds start conservative, are shown on screen, and are tuned only from officer feedback.**

### 8.4 Event-driven triggers (what makes it proactive)
When a bureau records a significant action (configurable list: show-cause, inspection ordered, approval withdrawal proceedings, penalty, disposal) on institution `I`, immediately check for open cases of **other** bureaus on `I` and alert their officers and heads **before** the action is finalised where the workflow allows a "pre-action coordination check" step.

### 8.5 Presentation and workflow
- Banner on case detail, institution profile and dashboard: **"Potential Overlapping Cases – Coordination Required"** with the involved bureaus, case IDs, statuses, last actions and the **reasons list**.
- Officer actions: **Confirm and link** (choose relationship), **Dismiss** (reason required, feeds tuning), **Start coordination** (thread, optional lead bureau, optional time-boxed T2 share), **Record decision** (`proceed in parallel` needs a reason, `consolidate under <bureau>`, `hold`). All audited, all real-time.
- Group by institution: one `overlap_group` per institution with member cases, so officers see the institution-level picture, not 40 pairs.
- `scripts/eval_overlap.py` computes precision/recall on officer-labelled pairs and writes `docs/overlap-eval.md`. Until labels exist, the UI shows "confidence: uncalibrated".

---

## 9. UI / UX DESIGN SYSTEM (Apple Liquid Glass on iOS, Material 3 on Android, one brand on web)

### 9.1 Principles
1. **One visual identity, three native skins.** Colour, shape, spacing and tone come from the reference image (9.2) on every platform. The *chrome* follows the platform: iOS uses Liquid Glass; Android uses Material 3 (Expressive where the installed library offers it); web uses the same tokens with CSS glass on the functional layer.
2. **Reference = look, not features.** The reference image is a smart-home app. Copy its **colour, gradients, corner radii, card depth, chips, pill navigation, chart styling and typography feel**. Do **not** copy rooms, devices, cameras, thermostats or energy features. Do not use its photos or any imagery from it.
3. **Glass is for the functional layer** (navigation bars, toolbars, sheets, floating controls, filter chips). Content cards stay solid and legible. This follows Apple's Liquid Glass guidance: glass belongs to controls and navigation floating above content, not to every surface.
4. **Government-grade legibility beats decoration.** Every text/background pair is WCAG 2.2 AA (GIGW 3.0 expects WCAG 2.1 AA at minimum). The reference puts white text on a light-blue gradient (about 3.3:1, fails AA). We keep the gradient look but move text onto the deep end of the gradient or use navy text on the light end (9.2).
5. **Dense where officers work, calm where they scan.** Dashboards are airy cards; case tables are dense with sticky headers.
6. **Never colour alone.** Every status has an icon and a label.

### 9.2 Reference analysis (measured from the image) and tokens

Measured dominant values: backdrop gradient `#032D45` to `#153F58` to `#2F7096` to `#439BCD`; card surfaces `#FFFFFF`, `#F7F7FC`, `#F1F4FA`, `#E4E7F0`; inactive chart bars and tints `#EAF9FF`; active bar and nav accent `#1787C7` to `#2496D5` to `#3DA7E3` to `#55BFFD`; headline navy `#0A2E45`. Shape language: phone shell about 40 px radius at the image scale, cards about 24, inner tiles about 18, chips and nav buttons fully rounded. Layout cues: gradient "summary pill" banners, soft-lavender cards on a blue field, chip filter rows with an outlined active chip, a **floating pill bottom navigation** whose active item expands into a gradient circle plus label, a **semi-circular gauge with tick marks**, **vertical bar charts with one highlighted gradient bar and a marker dot**, list rows with title, subtitle and a right-aligned value.

**Tokens** (single source `packages/ui-tokens`, generated to CSS variables, Tailwind `@theme`, React Native theme objects and the Android Material colour scheme; **no raw hex outside this package**, enforced by a lint rule):

| Token | Light | Dark | Use / verified contrast |
|---|---|---|---|
| `canvas` (gradient) | `radial-gradient(120% 90% at 70% 20%, #439BCD 0%, #2F7096 38%, #153F58 70%, #032D45 100%)` | `radial-gradient(120% 90% at 70% 15%, #134563 0%, #0D3753 45%, #06283D 100%)` | page backdrop (web, login, mobile headers) |
| `surface-0` | `#FFFFFF` | `#0D3753` | cards |
| `surface-1` | `#F7F7FC` | `#134563` | raised/inset tiles |
| `surface-2` | `#F1F4FA` | `#0B3048` | table stripes, inputs |
| `outline` | `#E4E7F0` | `#2A5775` | dividers, borders |
| `ink` | `#0A2E45` (14.1:1 on white) | `#E6F2FA` (10.9:1 on surface-0 dark) | primary text |
| `ink-muted` | `#5B7088` (5.1:1 on white, 4.78 on surface-1) | `#A9C4D8` (6.85:1) | secondary text |
| `brand-700` | `#0B5F94` (6.8:1 with white text) | | text-bearing gradient start |
| `brand-600` | `#0F6FA8` (5.4:1 with white text) | | links, text-bearing gradient end, under-process text |
| `brand-500` | `#1787C7` | | active bar, nav accent, focus ring (3.9:1 on white) |
| `brand-400` | `#2496D5` | | accents (decorative) |
| `brand-300` | `#3DA7E3` | | gradient mid |
| `brand-200` | `#55BFFD` (navy text 6.9:1) | | gradient light end, glow |
| `brand-100` | `#A6E0FF` | | highlights |
| `brand-50` | `#EAF9FF` | `#134563` | inactive chart bars, chip fill |
| `grad-deco` | `linear-gradient(135deg,#1787C7 0%,#3DA7E3 55%,#55BFFD 100%)` | same | **decorative only** (no body text) |
| `grad-text` | `linear-gradient(135deg,#0B5F94 0%,#0F6FA8 100%)` | same | summary pills carrying white text |
| `focus` | 2 px `#1787C7` + 2 px white offset | 2 px `#6CC4FF` | visible on every control |

**Status palette (text on tint, all >= 4.5:1; dark-mode text colours >= 5.4:1 on `#0D3753`):**
`pending` `#8A5A00` on `#FFF4DC`; `under_process` `#0F6FA8` on `#EAF9FF`; `disposed` `#0F7B4F` on `#E6F6EE`; `transferred` `#5B4BC4` on `#EEEBFF`; `escalated` `#B3411B` on `#FFEBE3`; `overdue` `#B42318` on `#FEECEA`; `overlap` (coordination) `#0B6B7A` on `#E3F6F8`. Dark: `#F5C451`, `#6CC4FF`, `#5FD3A0`, `#B7ACFF`, `#FF9B73`, `#FF8A80`, `#6FD6E3`. Each status pairs with an icon (Section 9.9) and a text label. `docs/design-contrast.md` is generated by a script that recomputes every pair and **fails CI below 4.5:1 (text) or 3:1 (non-text)**.

### 9.3 Typography, shape, spacing, elevation, motion
- **Web:** a geometric sans close to the reference feel (**Urbanist** or **Plus Jakarta Sans**, SIL OFL, self-hosted, `font-display: swap`) with **Noto Sans Devanagari** and **Noto Sans Tamil** fallbacks so Hindi and Tamil never render in tofu. Choose one by eye against the image in Phase 0 and log it. Scale 12/14/16/18/20/24/32/40; weights 400/500/600/700; tabular numerals for counts and dates.
- **iOS:** system font (SF Pro) with Dynamic Type. **Android:** Roboto Flex/Roboto (Material 3 type scale). Do not ship the web font in native apps.
- **Shape:** card 24, tile 18, input 14, button 16 (pill for primary mobile actions), chip/nav 999. **Spacing:** 4-pt grid, page gutters 16 (mobile) / 24 (tablet) / 32 (desktop).
- **Elevation:** one soft shadow family only, `0 8px 24px rgba(10,46,69,.12)` and `0 2px 8px rgba(10,46,69,.08)`; no hard borders on cards except `outline` at 1 px for tables and inputs.
- **Motion:** 180 to 280 ms ease-out for state changes, spring (`damping 18, stiffness 220`) for the active nav pill and sheet presentation; list updates from realtime events animate with a 600 ms highlight fade; **all motion honours reduce-motion**.

### 9.4 Glass rules (web and iOS)
- **Web:** `backdrop-filter: blur(24px) saturate(1.4)`; fill `rgba(255,255,255,.72)` light / `rgba(13,55,83,.6)` dark; 1 px inner border `rgba(255,255,255,.65)`; top highlight gradient 1 px. Use on: top command bar, sidebar rail, floating filter bar, popovers, command palette, dialogs. **At most three blurred layers in any viewport.** Provide fallbacks: `@supports not (backdrop-filter)` and `prefers-reduced-transparency` and `prefers-contrast: more` switch to opaque `surface-0` with an `outline` border.
- **iOS (26+):** use `expo-glass-effect` `GlassView` (`glassEffectStyle` regular for controls, clear only over media-rich areas) and `GlassContainer` for adjacent glass shapes that should merge; gate every use with `isLiquidGlassAvailable()`; fall back to a solid `surface-0` card with the same radius on iOS < 26 or when Reduce Transparency is on. Use `NativeTabs` (`expo-router/native-tabs`) so the tab bar and navigation headers get system glass automatically. Tint glass with `brand-500` at low alpha for the active element only. Never put body text directly on clear glass.
- **Dim/scrim:** where text sits on glass over the gradient canvas, add the platform-recommended dimming layer so contrast holds (verify with the contrast script on screenshots, not on tokens alone).

### 9.5 Android: Material 3
- Use `@expo/ui` Jetpack Compose components **only where the installed package version exposes them** (verify in the package's types before use) for switches, chips, sheets, date pickers, navigation bar and FAB; otherwise React Native primitives styled with tokens. Do not invent component names.
- **Colour:** brand-seeded Material 3 scheme generated from `#1787C7` (tonal palettes), so Android matches the reference. **Dynamic colour (Material You) is OFF by default** and offered as a user setting, because it would change the brand look.
- **Navigation:** Material 3 navigation bar with the pill active indicator (this is the Material equivalent of the reference's expanding active pill); navigation rail on tablets; large top app bar that collapses on scroll.
- **Icons: Material Symbols only** (`@expo/material-symbols`), Rounded style, weight 400, fill 0 for inactive and fill 1 for active. Android code may not import any other icon library (CI lint).

### 9.6 Dashboard composition (maps reference components to this product)

| Reference element | Becomes | Content (all computed from real rows) |
|---|---|---|
| Gradient summary pill ("1632kwh Synced 3 hours ago") | **Total cases banner** using `grad-text` | Total open cases, delta vs last week, "Updated <time>" with a live dot |
| Chip row (All, Living Room, Kitchen) | **Bureau/Cell chips** | All, RB, PGRC, others (from master data), plus Region and Status filters |
| Room cards with image | **Institution cards**, no photography | Monogram avatar from initials on `grad-deco`, name, AICTE Permanent ID, open/overdue counts, bureaus involved as mini chips, overlap badge |
| ON/OFF circular badges | **Status badges** | Icon + label per status (9.2) |
| Semi-circular gauge with ticks | **SLA compliance gauge** | % of open cases within timeline; needle/arc in `grad-deco`; below it "N beyond timeline" |
| Bar chart, one highlighted bar + marker | **Monthly received vs disposed** | Tap/hover a bar to highlight and show the exact numbers; inactive bars `brand-50` |
| List rows (title, subtitle, right value) | **Recent activity** and **Bureau workload rows** | Live feed (case ID, action, bureau, time); workload with open/overdue per bureau |
| Floating pill bottom nav | **Primary navigation (mobile)** | Home, Cases, Institutions, Alerts, More |
| Device-energy list ("Highly consumption") | **Pending ageing list** | Buckets with counts |

Add three product-specific tiles that the reference does not have: **Overlap queue** (count + top three institutions, banner colour `overlap`), **Beyond timeline** (critical list), **Transfers awaiting acceptance**. Required tiles from the problem statement: total received, pending, under process, disposed, transferred, beyond timeline, institution-wise status, bureau/cell-wise workload. Charts: ECharts 6 (tree-shaken: bar, gauge, line, heatmap, sankey) themed from tokens. A **Sankey of case movement between Bureaus/Cells** (transfers) is the signature chart. **Do not draw a geographic map of India** (boundary depictions are legally sensitive); use a **tile-grid cartogram or ranked bars** for region-wise views unless an official boundary dataset is supplied by AICTE.

### 9.7 Web screens (layout differs from mobile; look is identical)

**Shell:** left glass **sidebar rail** (collapsible to icons, active item = gradient pill like the reference nav), top glass **command bar** (global search with Ctrl/Cmd+K palette, live connection indicator, alerts bell with count, language switcher en/hi/ta, theme toggle, profile menu), content on a 12-column grid with max width 1440, blue canvas gradient behind white/soft cards. Breakpoints: >= 1280 full grid, 768 to 1279 rail collapsed and 8-column grid, < 768 bottom pill navigation like mobile. Split-view on wide screens: list left, detail right (case detail opens in a right panel, deep-linkable).

Screens: 1 Sign-in (glass card on canvas, TOTP step, lockout messaging); 2 **Command Dashboard** (role-aware); 3 **Cases** (dense table, filters, saved views, bulk assign/transfer, column picker, keyset paging); 4 **Case detail** (header with status stepper and SLA countdown, tabs: Timeline, Documents, Linked & Overlaps, Coordination, Parties (T2), Audit; right action drawer); 5 **Institutions** (search, cards/table toggle); 6 **Institution profile** (identity block with provenance badge, bureau-involvement matrix, consolidated case history, overlap panel); 7 **Overlap queue** (grouped by institution, reasons list, confirm/dismiss/coordinate); 8 **Coordination thread** (messages, lead bureau, decision record); 9 **Alerts centre** (filters, ack/snooze, rules view); 10 **Workload board** (bureau x officer, overdue share, reassign by drag-and-drop with keyboard alternative); 11 **Reports** (catalogue below, parameter form, preview, export, scheduled runs); 12 **Registration** (stepper form with duplicate pre-check) and **Intake queue**; 13 **Bulk import** (upload, mapping, dry run, progress, error report, rollback); 14 **Admin** (users and roles, Bureau/Cell/RO master, categories, SLA policies, holidays, escalation ladder, notification templates, integrations console, import jobs, audit viewer, integrity, config versions); 15 **Profile & security** (TOTP, sessions, notification preferences, data-rights requests); 16 **Help, Privacy, Accessibility, About**.

**Report catalogue (R11):** bureau/cell-wise; region-wise; institution-wise complaint history; status-wise; pending ageing analysis; disposal rate; overlapping/duplicate cases; transfer and escalation flow; monthly performance; quarterly performance. Each report shows its metric definitions, filters, "as of" time, and the SQL hash; exports carry the same footer.

### 9.8 Mobile screens (single column, thumb-first)
Tabs: **Home** (summary pill, tiles, gauge, overlap card, activity), **Cases** (search + chips + list; pull to refresh; swipe actions: acknowledge, add remark), **Institutions**, **Alerts** (inbox with ack/snooze), **More** (reports summary, profile, security, language, theme, about). Case detail is a push screen with sticky status header and segmented control (Timeline, Docs, Overlaps, Chat). Role-aware: `registry_operator` gets a **Register case** FAB and intake queue; `regional_officer` gets region-scoped views and a field-note composer; `competent_authority` and `senior_management` get a digest-first Home. **Actions that need step-up use biometrics** (`expo-local-authentication`) with PIN/TOTP fallback. Push notifications (`expo-notifications`, FCM/APNs through Expo Push) deep-link to the case/alert; **tokens registered per device and revoked on sign-out**. Offline: read-only cache of the last dashboard, case lists and the user's open cases; drafts of remarks saved locally and sent when online; **no offline state changes**. Realtime: WebSocket in foreground with SSE/poll fallback; push in background.

### 9.9 Icons
- **Android and web:** Material Symbols Rounded only. **iOS:** SF Symbols via `expo-symbols`. One abstraction `<Icon name="case-pending" />` backed by a **complete** mapping table in `packages/ui-tokens/src/icons.ts` (semantic name to SF Symbol and Material Symbol). Coverage must be 100% of icons used (the previous build covered 6 of 40). Validate every name against the installed symbol set at build time (a script that fails on an unknown name). CI lint bans other icon libraries and emoji-as-icon. Web uses a self-hosted Material Symbols subset (only used glyphs) for size and CSP.
- Required semantic icons include: dashboard, cases, institution, alert, overlap/link, transfer, escalate, dispose, pending, under-process, overdue, remark, document, timeline, search, filter, report, export, region, bureau, officer, settings, security, language, help, sign-out, refresh, live-connection.

### 9.10 States, accessibility, internationalisation
- Every screen implements **loading (skeletons), empty (honest, with the next action), error (retry), partial, offline, no-permission** states. Empty dashboards say "No cases registered yet", never a made-up number.
- **WCAG 2.2 AA**: keyboard-complete, visible focus, 44x44 pt targets (24x24 CSS px minimum on web), labelled controls, live regions for realtime updates (polite), no colour-only meaning, zoom to 200% and 400% reflow, Reduce Motion and Reduce Transparency honoured, screen-reader tested (VoiceOver, TalkBack, NVDA). GIGW 3.0 compliance checklist in `docs/gigw-checklist.md` (88 mandatory checkpoints per the published summary; verify against the official guidelines).
- **i18n:** English, Hindi, Tamil from day one with ICU message format, locale-aware dates (IST), Indian numbering (lakh/crore) for counts in the UI, no string concatenation, pseudo-locale test. Hindi and Tamil text must be marked "machine-reasoned, needs native review" in the decision log until reviewed.

### 9.11 UI quality gates (what "done" means for design)
1. Tokens package exists and is the only source of colour/spacing/type.
2. A **component gallery** (Storybook or a `/dev/gallery` route) shows every component in every state, light and dark.
3. Playwright screenshots (1440x900, 1024x768, 390x844) of every screen in light and dark stored under `docs/ui-evidence/`; axe-core has zero serious/critical violations; Lighthouse accessibility >= 95 on the dashboard and cases pages.
4. Mobile: screenshots from an **iOS 26 simulator/device (glass)**, an iOS < 26 fallback, and an **Android device/emulator (Material 3)** for every tab and the case detail; Maestro flows run and recorded. If no device is available, the AI must say **"mobile visual QA not performed"** and may not tick the gate.
5. A written **design-fidelity review** compares screenshots side by side with `ui-refrence-iamge.png` (palette, radii, gradient, nav, chart style) and lists deviations with reasons (e.g. text contrast fixes).
6. A CI check fails if any `.tsx` page renders raw `<table>`, `<button>`, `<input>` or `<select>` without the design-system components, or if a screen lacks a screenshot baseline.

---

## 10. BACKEND ARCHITECTURE (lightweight, powerful, real-time)

**Shape:** modular monolith plus one worker, five containers behind Caddy: `api`, `worker`, `postgres`, `valkey`, `proxy`. No Kubernetes, Kafka, Elasticsearch or microservices: the workload is bounded (officers, not the public), correctness and auditability matter more than horizontal scale, and a single VM must run it. Everything is 12-factor so it can move to NIC/MeghRaj or any cloud unchanged.

**Stack (versions in Section 15):** Python 3.12+, FastAPI, Pydantic v2 (`extra="forbid"`), SQLAlchemy 2 async + Alembic, PostgreSQL 18 with `pg_trgm`, `unaccent`, `btree_gin`, `pg_stat_statements` (add `pgvector` only if embeddings are stored; otherwise compute on the fly), Valkey (stable tag verified on the day), ARQ (async jobs; **record an ADR confirming ARQ's maintenance status before committing**, alternative Dramatiq), `orjson`, `structlog`, OpenTelemetry, Sentry-compatible error reporting (inert without a DSN and shown as such).

**Request pipeline (12 steps, every endpoint):** request ID, auth, session/step-up check, rate limit, input validation, authorisation (`can`), begin transaction with RLS context, business logic, event + projection + counters + outbox + audit in one transaction, commit, response, post-commit publish by relay.

**API:** `/api/v1`, OpenAPI is the contract; the web and mobile clients use one generated TypeScript client (`openapi-typescript` + `openapi-fetch`); problem+json errors; **keyset pagination everywhere** (the previous build returned unbounded lists); ETag/If-None-Match on read models; `Idempotency-Key` on every POST; bulk endpoints return a job resource.

**Performance design (targets, to be measured and published in `docs/perf.md`):** lists from indexed projections only; composite indexes on `(institution_id, status)`, `(bureau_id, status, due_at)`, `(region_id, status)`, GIN on search vectors, trigram indexes on institution names; `case_events` partitioned monthly; dashboard tiles read from `dashboard_counters` (O(1)); heavy aggregates from materialized views; connection pooling (PgBouncer optional); capacity assumptions (not facts) of 10^5 cases, 10^4 institutions and 10^3 concurrent officers are used for load tests with **synthetic data generated only inside the load-test tool and only in a throwaway database**.

**Workers:** outbox relay, SLA scanner (every minute, idempotent), alert dispatcher, overlap evaluator (consumes `case.*` events), report runner, import runner (chunked, resumable), nightly jobs (projection replay check, counter reconciliation, integrity recheck, audit-head anchor, key-rotation job when scheduled).

**Search:** PostgreSQL full-text (`simple` config + `unaccent`) plus trigram for names; no external search engine.

---

## 11. CLIENT STACKS (pinned; verified on 28 Oct 2026)

### 11.1 Web
Vite 8 + React 19 + TypeScript (**if the installed toolchain does not support TypeScript 7, pin the latest 6.x and log it**), TanStack Router, TanStack Query, TanStack Table + Virtual, React Hook Form + Zod 4, Tailwind CSS 4 with the generated `@theme` tokens, Radix primitives behind the in-house components, ECharts 6, `motion`, i18next, `openapi-fetch`. Single-page app served by Caddy on the same site as the API (cookies, CSRF, no CORS surface). Route-level code splitting; budgets: login route <= 150 KB gzipped JS, dashboard <= 350 KB, Lighthouse performance >= 90 on a mid-range laptop profile. **A framework change (e.g. Next.js) needs an ADR; the default is the SPA because the app is authenticated, not SEO-driven.**

### 11.2 Mobile
Expo SDK 58, React Native 0.88, Expo Router (`expo-router` **58.x**, `NativeTabs` from `expo-router/native-tabs`), `expo-glass-effect` (iOS), `@expo/ui` (SwiftUI/Jetpack Compose controls), `expo-symbols` (iOS), `@expo/material-symbols` (Android), `expo-notifications`, `expo-local-authentication`, `expo-secure-store`, TanStack Query, Zustand, FlashList 2, Reanimated 4. Strict TypeScript API is the default in SDK 58. Release builds enable R8 on Android. Run `npx expo install --fix` and `npx expo-doctor` in CI. Free distribution: Expo development builds and Android APK; store publishing is outside free-tier scope.

---

## 12. DEPLOYMENT, CI/CD, OBSERVABILITY

- **Primary free target:** Oracle Cloud Always Free Ampere A1 VM (2 OCPU, 12 GB) with Docker Compose + Caddy (automatic TLS). Documented risk: idle-reclamation of free instances; mitigate with real usage and monitoring, do not fake load. **Production target for a real adoption is AICTE/NIC-controlled hosting**; keep the app portable. Neon free tier only for staging or backup restore tests (it suspends idle databases, so it is unsuitable for realtime).
- **Compose services:** `proxy` (Caddy 2), `api`, `worker`, `postgres:18`, `valkey` (pin the verified stable tag), optional `clamav`. Resource limits per container; healthchecks; non-root users; read-only root filesystems where possible; secrets from env files outside the repo (`.env` files are never committed or zipped; **the uploaded archive of the previous build contained `.env`, `.aws`, `.codex` folders: rotate anything real in them and exclude them from future archives**).
- **Database roles:** `app_owner` (migrations only), `app_runtime` (least privilege, RLS-bound, no UPDATE/DELETE on `case_events` and `audit_log`), `app_readonly` (reports). The previous build's runtime role was already least-privilege, but its **owner role was a Postgres superuser**; narrow it before any non-local run.
- **Backups:** nightly encrypted `pg_dump` + WAL archiving where available; **restore rehearsal in CI/staging monthly with a recorded result**; RPO/RTO stated in the runbook as targets.
- **CI (GitHub Actions):** lint, typecheck, unit, integration (real Postgres + Valkey services), web e2e (Playwright), visual snapshots, axe, mobile typecheck + `expo-doctor` + Maestro (where runners allow), Gitleaks, Semgrep, Bandit, pip-audit, npm audit, Trivy (images), Syft SBOM, ZAP baseline against the composed stack, contrast script, icon and data-origin guards. All jobs must have **actually run green on GitHub**, not only locally.
- **Observability:** structured JSON logs with request ID, no personal data in logs; Prometheus-style `/metrics` (protected); OpenTelemetry traces; dashboards for latency, error rate, queue depth, outbox lag, WS connections, SLA scanner lag; alerts to `super_admin`.

---

## 13. TESTING (each acceptance criterion in Section 2.1 maps to a test)

Unit (rules, business-day engine, similarity scoring, authz matrix) with property tests (`hypothesis`); integration against real Postgres/Valkey including **RLS cross-bureau and cross-region leak tests, T1/T2/T3 visibility tests, outbox atomicity (kill the worker mid-transaction), resume-after-disconnect, counter reconciliation, projection replay equality**; contract tests from OpenAPI; Playwright e2e per role; visual regression; axe; Maestro for mobile; load test (Locust, throwaway DB) for the capacity assumptions; chaos tests (Valkey down, DB down, worker crash mid-import, clock skew); security tests (OWASP ASVS L2 checklist, upload abuse, CSV injection, IDOR on every resource, WS subscription to an unauthorised channel, refresh token reuse). Coverage targets: authz and rules >= 95%, overall >= 80%. **Mutation test** (`mutmut` or equivalent) on the SLA engine and overlap scorer.

---

## 14. DEMO SCRIPT (state whether data is pilot/real or TEST sandbox)

1. Sign in as `bureau_head` (RB) with TOTP; show the live dashboard and the "Updated" live dot.
2. As `registry_operator`, register a case against a real institution from the imported master; show the duplicate pre-check.
3. As PGRC `case_officer`, register a second case on the same institution with different wording; on the RB screen the **"Potential Overlapping Cases – Coordination Required"** banner appears live, with reasons.
4. Open the coordination thread, record "consolidate under PGRC" with a reason; both screens update live.
5. Transfer a case between bureaus (step-up auth); watch the Sankey and bureau workload update.
6. Time-travel is **not** used in the demo: show a case whose real due date is near, or the SLA configuration and alert history; show the SLA gauge.
7. Generate the bureau-wise report, open the XLSX, show the footer (filters, hash, as-of time).
8. Open the iOS app (Liquid Glass) and the Android app (Material 3): push notification arrives, deep-links to the case, biometric step-up for escalation.
9. Show the audit chain verification and the Integrations Console (`NOT_CONFIGURED` CPGRAMS feed, said out loud).

---

## 15. VERIFIED FACTS, VERSIONS, SOURCES AND OPEN ITEMS

**Verified on 28 Oct 2026**
- AICTE PGRC scope (grievances, complaints and malpractices; students, faculty and stakeholders; CPGRAMS grievances; ragging; norm violations; VIP/Ministry references; court cases; Parliament questions; RTI; miscellaneous): aicte.gov.in/node/422. The page gives **no timelines, officers or appeal process**.
- AICTE bureaus page lists: Approvals Bureau (under "Regulation"), Administration, Finance, Policy & Academic Planning, Scholarships and Grants, Training-and-learning, and a Special Cell for Research and Coordination with State Govts/UTs: aicte.gov.in/bureaus. **Wikipedia lists eight differently named bureaus and 12 regional offices** (Kanpur, Chandigarh, Gurugram, Mumbai, Bhopal, Vadodara, Kolkata, Guwahati, Bengaluru, Hyderabad, Chennai, Thiruvananthapuram). The two sources disagree; AICTE's own "ROs Details" PDF could not be fetched. **Therefore Bureau/Cell and Regional Office master data is admin-editable and seeded from the official page, with an open item to confirm with AICTE.**
- DARPG Comprehensive Guidelines (OM 23.08.2024): standard 21 days; priority grievances 3 days; interim ATR when longer; forward misrouted grievances within 48 hours; appeals 30 days; Nodal PG Officer, GRO, Nodal Appellate Authority roles; grievances must not be closed as "not our subject" but transferred; only the concerned authority registers in CPGRAMS to avoid duplicates (staffnews summary; official PDF at pgportal.gov.in).
- PIB (Aug 2026): CPGRAMS routing to mapped last-mile officers; excluded matters (RTI, court/sub-judice, religious, service matters); NextGen CPGRAMS in development with omni-channel intake and automated escalation; **no API described**.
- `facilities.aicte-india.org` dashboard: automated fetch disallowed by robots rules. data.gov.in AICTE-related resource found: aggregate table, "The API for this resource does not exist".
- Publicly visible Permanent ID examples: `1-461530291`, `1-7010229243` (pattern `1-` + 9 to 10 digits; regex stays configurable).
- GIGW 3.0 (secondary source, digit.in, 29 Aug 2025): 88 mandatory checkpoints, WCAG 2.1 AA, OWASP/ISO 27001 alignment, mobile apps in scope. Confirm against guidelines.india.gov.in.
- Expo SDK 58: React Native 0.88; `expo-router/native-tabs` import path; `@expo/ui` and `expo-symbols` optional peers; Android R8 on by default; scene-based iOS lifecycle (Expo upgrade blog).
- DPDP Rules 2025 notified 13 Nov 2025; commencement 14 Nov 2025, 14 Nov 2026 and 14 May 2027 (research of 27 Oct 2026).

**Package versions checked on 28 Oct 2026 (npm / PyPI)**
`react 19.3.1`, `vite 8.3.5`, `typescript 7.0.2`, `tailwindcss 4.3.3`, `@tanstack/react-query 5.105.0`, `@tanstack/react-router 1.170.46`, `@tanstack/react-table 9.3.1`, `@tanstack/react-virtual 3.14.23`, `zod 4.6.7`, `react-hook-form 7.91.0`, `echarts 6.1.0`, `motion 14.7.1`, `i18next 26.5.11`, `openapi-typescript 7.13.0`, `zustand 5.0.16`, `@playwright/test 1.64.1`, `vitest 5.0.5`; `expo 58.0.20`, `react-native 0.88.1`, `expo-router 58.0.27`, `expo-glass-effect 58.0.5`, `@expo/ui 58.0.24`, `expo-symbols 58.0.4`, `@expo/material-symbols 0.1.1`, `expo-notifications 58.1.6`, `expo-local-authentication 58.0.2`, `expo-secure-store 58.0.2`, `@shopify/flash-list 2.3.3`, `react-native-reanimated 4.7.1`; `fastapi 0.162.0`, `pydantic 2.14.1`, `sqlalchemy 2.1.6`, `alembic 1.20.1`, `asyncpg 0.32.0`, `arq 0.28.0`, `uvicorn 0.54.0`, `rapidfuzz 3.14.6`, `pyotp 2.10.0`, `argon2-cffi 25.1.0`, `structlog 26.1.0`, `opentelemetry-sdk 1.45.1`, `pytest 9.2.0`, `hypothesis 6.170.12`, `locust 2.47.0`, `fastembed 0.9.1`, `onnxruntime 1.31.1`, `holidays 0.107`. PostgreSQL 18.6 from the earlier verified research; **Valkey: confirm the latest stable tag on the day (8.x expected, not verified here)**. Re-check every version on the day you install.

**Open items (resolve in `docs/decision-log.md`, do not guess)**
1. Official list of Bureaus/Cells and Regional Offices and which of them handle complaints. 2. Real nature-of-complaint taxonomy and SLA for non-CPGRAMS case types. 3. CPGRAMS export format or API access for AICTE. 4. AICTE Permanent ID exact format. 5. Whether the complaint mailbox can be integrated. 6. Retention schedule for case records. 7. Whether AICTE wants NIC SSO. 8. DPDP exemption status. 9. Multilingual embedding model quality on real Hindi/Tamil complaint text and licence check. 10. ARQ maintenance status (ADR). 11. Valkey Streams test. 12. TypeScript 7 toolchain compatibility. 13. Hindi/Tamil native review. 14. Whether a boundary dataset for maps will be provided by AICTE.

---

## 16. PHASES AND GATES (UI is inside every phase)

**Phase 0: Foundations, decisions, design system first.** Monorepo (pnpm + Turborepo: `apps/web`, `apps/mobile`, `packages/ui-tokens`, `packages/ui-web`, `packages/ui-native`, `packages/api-client`, `packages/i18n`, `backend`, `rules` (overlap + SLA pure libraries), `infra`, `docs`). ADRs for every Section 15 open item that blocks work. Tokens package with Section 9.2 values, contrast script, component gallery with the shell, buttons, inputs, chips, cards, tiles, gauge, bar chart, table, status badge, pill navigation in light and dark. CI skeleton with all guards. Valkey Streams test. **Gate:** gallery screenshots reviewed against the reference image; contrast script green; CI green on GitHub; a login screen already styled.

**Phase 1: Identity, RBAC, RLS, audit.** Sections 4 and 7.4: auth, TOTP, lockout, rate limits, cookie+CSRF web session, refresh rotation, step-up, roles, assignments, T1/T2/T3 visibility, RLS, audit hash chain with external anchor, key-rotation job. **Gate:** generated permission-matrix test over every endpoint; cross-bureau and cross-region leak tests; styled sign-in, profile/security and admin-users screens.

**Phase 2: Reference data and master data.** Importer with provenance and review queue; institutions, aliases, Bureau/Cell and RO master (editable, versioned); Institutions list and profile (empty case history honest). **Gate:** real imported institutions visible with source badge; diff view; no synthetic data guard green; screenshots.

**Phase 3: Case lifecycle.** Registration with duplicate pre-check, intake queue, event log, projection, counters, workflow actions, documents, transfers (propose/accept/reject), escalation, disposal, reopen, bulk import with preview/dry run/chunked/resumable/rollback, formula-safe error report. **Gate:** R3 and R8 tests; projection replay equality; counter reconciliation; styled registration, cases table, case detail, import screens.

**Phase 4: Overlap engine and coordination.** Section 8 end to end including institution resolution, event-driven triggers, grouped queue, coordination threads, shares, decisions, `eval_overlap.py` harness (runs on whatever labelled pairs exist; "uncalibrated" label otherwise). **Gate:** R4, R5, R6, R12 tests incl. different-wording and different-institution negatives; banner screens.

**Phase 5: SLA, alerts, real-time.** Business-day engine, policies, scanner, alert catalogue, escalation ladder, notification dispatch, outbox/relay/WS/SSE with resume and per-channel auth. **Gate:** R10 and R13 tests; kill-worker and reconnect tests; latency measured and written to `docs/perf.md`.

**Phase 6: Dashboard, search, reports.** Section 9.6 and 9.7 and Section 6.5: tiles, gauge, bar, Sankey, ageing, workload, search filters (R9), saved views, report catalogue, exports with watermark/hash, scheduled runs. **Gate:** R7, R9, R11 tests; tile equals list count; all report totals equal dashboard totals; full web screenshot pack.

**Phase 7: Mobile.** Section 9.5, 9.8, 11.2: Expo app for iOS (Liquid Glass with fallback) and Android (Material 3), push, biometrics, offline read cache, realtime. **Gate:** runs on real devices or simulators with the Maestro flow and the screenshot pack; or the phase is reported **"mobile visual QA not performed"** and does not pass.

**Phase 8: Hardening.** ZAP, Semgrep, SBOM, dependency audit, ASVS L2 checklist, GIGW checklist, accessibility audit with screen readers, load and chaos tests, key-rotation rehearsal, backup restore rehearsal. **Gate:** every scanner actually run; zero high/critical open; results in `docs/`.

**Phase 9: Deploy and demo.** Oracle A1 deployment, TLS, backups, monitoring, runbook, demo rehearsal (timed), pitch deck notes with honest limits, final `docs/limitations.md` rewrite. **Gate:** public URL, uptime check, demo rehearsed and recorded.

---

## 17. FIRST ACTION

Do **not** write application code yet. Produce the **Phase 0 kickoff**: (a) architecture summary with a diagram; (b) repo layout; (c) the ADR list from Section 15 open items with how each will be verified; (d) the tokens package spec with the Section 9.2 values and the contrast script plan; (e) the component gallery screen list; (f) the CI job list; (g) risks. Then wait for approval.

---

## APPENDIX A: DEFECTS FOUND IN THE PREVIOUS BUILD (SIH-PS-2.zip, APAAR, SIH26263). Do not repeat any.

Verified by reading the archive on 28 Oct 2026 (about 4,000 lines of source across web, mobile, backend and rules):
1. **Web UI is unstyled HTML**: no CSS file exists; `index.html` has no stylesheet; pages are `<table>`, `<button>`, `<input>`. That is exactly the screenshot you saw. Root cause: the master prompt said the design system was "Phase 5/7 work", and each phase's limitations file recorded "no design applied" instead of failing the gate.
2. **`packages/ui-tokens` contains only an icon table** (no colours, type, spacing). Icon coverage 6 of 40 names; names unverified against the symbol sets.
3. **Web has 5 screens** (login, student list, student detail, flags, integrations) of the dozens required; state-based navigation instead of a router; in-memory auth that **logs out on refresh**; no data-fetching library; no charts; no pagination; 3 e2e test cases.
4. **Mobile has 2 screens** (login, dashboard); never `pnpm install`-ed or run on a device; `expo-router` pinned `~6.0.0` against Expo SDK 58 (current `expo-router` is 58.x); no Liquid Glass, no Material 3, no push, no biometrics, no offline.
5. **Backend list endpoints return unbounded results** (no limit/offset/cursor found); no security headers anywhere (API middleware or Caddyfile; Caddy listens on plain `:80` with no TLS/HSTS/CSP and still serves a placeholder string instead of the web app); no rate limiting or lockout; audit chain without external anchor; encryption with a single static key and no rotation; owner/migration role was a Postgres superuser (runtime role was least-privilege); PostgreSQL 16 and Redis 7 in Compose although the prompt specified PostgreSQL 18 and Valkey; worker is a poll loop, not a job queue; no SSE fallback, no resume on reconnect; bulk upload has no chunking or rollback; data-rights decisions did not mutate data; verification codes not bound to a verifier; flag-resolution notes discarded; only 6 of about 14 rules; no programmes/intake tables so key rules could not exist.
6. **Process failures to avoid:** phases were marked complete with large "not built" lists; ZAP never run; CI never run on GitHub; no SBOM; Sentry inert; nothing deployed. **Rules 3 and 9 in Section 0 exist to stop this.**
7. **Hygiene:** the archive included `.env`, `.aws`, `.codex`, `.arena`, `.playwright-mcp`, `node_modules` and build caches (about 750 MB uncompressed). Keep secrets and caches out of archives and out of Git.

## APPENDIX B: WHAT TO REUSE FROM THE PREVIOUS REPOSITORY (copy, then re-test; do not trust)
Reusable patterns: monorepo layout and CI guard scripts (`check-data-origin.sh`, `check-icon-imports.sh`), Argon2id/JWT/refresh-family logic in `core/security.py`, RLS session helper in `core/db.py`, the transactional outbox + relay + WS ticket modules in `realtime/`, the audit hash-chain service, the adapter base with `LIVE/SANDBOX/NOT_CONFIGURED/UNAVAILABLE`, the pure rules-engine package shape, i18n package scaffolding. **Do not reuse** anything APAAR-specific (students, `apaar_registry`, verification codes, APAAR rules). Every reused file must come with new tests and must pass the Phase 1 gate on its own.
