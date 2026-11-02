/**
 * Single source of truth mapping a semantic icon name to its per-platform
 * system icon (Section 9.9). Web/mobile code must import icons only
 * through this table — enforced by scripts/check-icon-imports.sh in CI —
 * never a third-party icon library or an emoji used as an icon.
 *
 * SF Symbol and Material Symbol (Rounded, weight 400) names here are a
 * starting set and are NOT yet confirmed against the live SF Symbols app /
 * Material Symbols catalog — tracked as a Phase 7 pre-gate check in
 * docs/decision-log.md. Every name used anywhere in the app must appear
 * here (coverage is validated at build time, not just declared).
 */
export interface IconSpec {
  ios: string;
  android: string;
}

export const icons = {
  // Required semantic set (Section 9.9)
  dashboard: { ios: "square.grid.2x2", android: "dashboard" },
  cases: { ios: "folder", android: "cases" },
  institution: { ios: "building.columns", android: "account_balance" },
  alert: { ios: "bell.badge", android: "notifications_active" },
  "overlap-link": { ios: "link", android: "link" },
  transfer: { ios: "arrow.left.arrow.right", android: "sync_alt" },
  escalate: { ios: "arrow.up.circle", android: "arrow_circle_up" },
  dispose: { ios: "checkmark.seal", android: "task_alt" },
  pending: { ios: "clock", android: "schedule" },
  "under-process": { ios: "gearshape.arrow.triangle.2.circlepath", android: "autorenew" },
  overdue: { ios: "exclamationmark.triangle.fill", android: "report" },
  remark: { ios: "text.bubble", android: "comment" },
  document: { ios: "doc", android: "description" },
  timeline: { ios: "clock.arrow.2.circlepath", android: "history" },
  search: { ios: "magnifyingglass", android: "search" },
  filter: { ios: "line.3.horizontal.decrease.circle", android: "filter_alt" },
  report: { ios: "chart.bar.doc.horizontal", android: "summarize" },
  export: { ios: "square.and.arrow.up", android: "ios_share" },
  region: { ios: "map", android: "map" },
  bureau: { ios: "building.2", android: "corporate_fare" },
  officer: { ios: "person.badge.key", android: "badge" },
  settings: { ios: "gearshape", android: "settings" },
  security: { ios: "lock.shield", android: "encrypted" },
  language: { ios: "globe", android: "translate" },
  help: { ios: "questionmark.circle", android: "help" },
  "sign-out": { ios: "rectangle.portrait.and.arrow.right", android: "logout" },
  refresh: { ios: "arrow.clockwise", android: "refresh" },
  "live-connection": { ios: "dot.radiowaves.left.and.right", android: "podcasts" },

  // Case statuses not already covered above
  disposed: { ios: "checkmark.circle.fill", android: "check_circle" },
  transferred: { ios: "arrow.triangle.swap", android: "swap_horiz" },
  escalated: { ios: "exclamationmark.arrow.triangle.2.circlepath", android: "priority_high" },
  overlap: { ios: "person.2.badge.gearshape", android: "groups" },

  // Coordination / overlap engine (Section 8)
  "institution-unresolved": { ios: "questionmark.square.dashed", android: "help_center" },
  coordination: { ios: "bubble.left.and.bubble.right", android: "forum" },
  "lead-bureau": { ios: "star.circle", android: "military_tech" },

  // Workflow / audit / integrity (Section 7.4, M14)
  "audit-log": { ios: "list.bullet.rectangle", android: "receipt_long" },
  integrity: { ios: "checkmark.shield", android: "verified_user" },
  "integrity-mismatch": { ios: "exclamationmark.shield", android: "gpp_bad" },
  confidential: { ios: "eye.slash", android: "visibility_off" },

  // Intake / import
  upload: { ios: "arrow.up.doc", android: "upload_file" },
  "upload-progress": { ios: "clock.arrow.circlepath", android: "progress_activity" },
  "intake-queue": { ios: "tray.full", android: "inbox" },

  // Integrations console (Section 3)
  integrations: { ios: "puzzlepiece.extension", android: "extension" },
  "not-configured": { ios: "minus.circle", android: "block" },

  // Auth / step-up (Section 4.1)
  totp: { ios: "key", android: "vpn_key" },
  biometric: { ios: "faceid", android: "fingerprint" },

  // Privacy / data rights (M15)
  "data-rights": { ios: "hand.raised.square.on.square", android: "privacy_tip" },
  "correction-request": { ios: "pencil.and.outline", android: "edit_note" },
  "erasure-request": { ios: "trash", android: "delete" },

  // Misc
  accessibility: { ios: "figure.roll", android: "accessibility_new" },
  "saved-view": { ios: "bookmark", android: "bookmark" },
  workload: { ios: "chart.bar", android: "bar_chart" },
} as const satisfies Record<string, IconSpec>;

export type IconName = keyof typeof icons;
