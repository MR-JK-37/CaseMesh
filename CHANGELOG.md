# Changelog

All notable changes to the CaseMesh repository are documented in this file.

## [Unreleased]

### Added
- **Rules Engine (`rules`)**:
  - Overlap level predicate helpers (`is_high_overlap`, `is_potential_overlap`, `is_info_overlap`).
  - Reason inspection and scoring utilities (`get_overlap_reason_codes`, `has_overlap_reason`, `calculate_time_proximity_score`, `get_shared_references`, `has_any_shared_external_reference`, `calculate_days_between_cases`, `count_shared_references`).
  - Institution candidate filtering and resolution helpers (`filter_candidates_by_min_score`, `is_resolution_matched`, `get_top_candidate`, `get_top_candidate_score`, `get_top_n_candidates`, `get_candidate_by_id`, `has_matching_permanent_id`, `has_matching_district_and_state`, `is_institution_candidate_active`, `is_valid_resolution_status`).
  - Text normalization tokenization and Jaccard similarity calculators (`tokenize_normalized_text`, `calculate_token_jaccard`, `normalize_external_reference`).
  - Case metadata and bureau predicates (`is_same_bureau`, `is_cross_bureau_pair`, `is_recent_case`, `get_matter_type`, `has_description`, `get_external_references_count`, `format_case_reference_summary`, `get_all_category_names`, `is_valid_matter_category`).
  - Test helper factory `create_case_facts` for reproducible testing.
- **UI Tokens (`@icm/ui-tokens`)**:
  - Typography letter spacing tokens (`tighter`, `tight`, `normal`, `wide`) and key types.
  - Shape specification z-index scale tokens (`base`, `card`, `header`, `dropdown`, `modal`, `toast`, `tooltip`).
  - Shape and typography token accessors (`getRadius`, `getElevation`, `getSpacingGutter`, `getZIndex`, `getMotionDuration`, `getSpringConfig`, `getGutterKeys`, `getFontWeight`, `getLineHeight`, `getLetterSpacing`, `getScaleStep`).
  - Color helpers and token accessors (`isBrandToneKey`, `getStatusColor`, `isValidStatusKey`, `getStatusForeground`, `getStatusBackground`).
- **UI Components (`@icm/ui-web`)**:
  - Exported standard props interfaces across `Card`, `Tile`, `GlassSurface`, `Icon`, `Gauge`, `BarChart`, `StatusBadge`, `Input`, `Table`, `Chip`, and `PillNav`.
  - Accessible `aria-label`, `aria-pressed`, and table caption attributes for keyboard and screen-reader navigation.
  - Safe theme token color references replacing raw color literals across application pages.
- **Backend Core & Models (`backend`)**:
  - Canonical constants and predicate helpers for `CASE_STATUSES`, `MATTER_TYPES`, `PRIORITIES`, `SOURCE_CHANNELS`, `DISPOSAL_TYPES`, `COMMUNICATION_CHANNELS`, `ESCALATION_LEVELS`, `ALERT_SEVERITIES`, and `REPORT_FORMATS`.
  - Batch permission checks `can_any`, `can_all`, action filter `get_permitted_actions`, and policy predicates (`can_manage_users`, `can_verify_institutions`, `can_read_audit_logs`, `can_ack_alerts`, `can_import_institutions`, `can_manage_bureaus`) in authorization policy.
  - Enhanced security and sanitation helpers (`mask_email`, `truncate_for_log`, `is_argon2_hash`, `is_valid_uuid`, `generate_secure_random_string`, `is_valid_sha256_hex`, `sanitize_alphanumeric_code`, `is_valid_email_format`, `mask_phone_number`, `is_valid_hex_color`, `sanitize_sql_like_pattern`, `generate_case_tracking_code`, `mask_account_number`).
- **Internationalization (`@icm/i18n`)**:
  - Common action and navigation translation keys across English (`en`), Hindi (`hi`), and Tamil (`ta`).
