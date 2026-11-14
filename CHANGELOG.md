# Changelog

All notable changes to the CaseMesh repository are documented in this file.

## [Unreleased]

### Added
- **Rules Engine (`rules`)**:
  - Overlap level predicate helpers (`is_high_overlap`, `is_potential_overlap`, `is_info_overlap`).
  - Reason inspection and scoring utilities (`get_overlap_reason_codes`, `has_overlap_reason`, `calculate_time_proximity_score`, `get_shared_references`).
  - Institution candidate filtering and resolution helpers (`filter_candidates_by_min_score`, `is_resolution_matched`, `get_top_candidate`, `get_top_n_candidates`, `has_matching_permanent_id`, `has_matching_district_and_state`).
  - Text normalization tokenization and Jaccard similarity calculators (`tokenize_normalized_text`, `calculate_token_jaccard`, `normalize_external_reference`).
  - Cross-bureau comparison predicate `is_cross_bureau_pair`, case recency check `is_recent_case`, and category utilities (`get_all_category_names`, `is_valid_matter_category`).
  - Test helper factory `create_case_facts` for reproducible testing.
- **UI Tokens (`@icm/ui-tokens`)**:
  - Typography letter spacing tokens (`tighter`, `tight`, `normal`, `wide`) and key types.
  - Shape specification z-index scale tokens (`base`, `card`, `header`, `dropdown`, `modal`, `toast`, `tooltip`).
  - Shape and typography token accessors (`getRadius`, `getElevation`, `getSpacingGutter`, `getZIndex`, `getFontWeight`, `getLineHeight`, `getLetterSpacing`).
  - Helper functions `isBrandToneKey` and `getStatusColor`.
- **UI Components (`@icm/ui-web`)**:
  - Exported standard props interfaces across `Card`, `Tile`, `GlassSurface`, `Icon`, `Gauge`, `BarChart`, `StatusBadge`, `Input`, `Table`, `Chip`, and `PillNav`.
  - Accessible `aria-label`, `aria-pressed`, and table caption attributes for keyboard and screen-reader navigation.
  - Safe theme token color references replacing raw color literals across application pages.
- **Backend Core & Models (`backend`)**:
  - Canonical constants and predicate helpers for `CASE_STATUSES`, `MATTER_TYPES`, `PRIORITIES`, `SOURCE_CHANNELS`, `DISPOSAL_TYPES`, and `COMMUNICATION_CHANNELS`.
  - Batch permission checks `can_any`, `can_all`, and action filter `get_permitted_actions` in authorization policy.
  - Enhanced security helpers (`mask_email`, `truncate_for_log`, `is_argon2_hash`, `is_valid_uuid`, `generate_secure_random_string`, `is_valid_sha256_hex`, `sanitize_alphanumeric_code`).
- **Internationalization (`@icm/i18n`)**:
  - Common action and navigation translation keys across English (`en`), Hindi (`hi`), and Tamil (`ta`).
