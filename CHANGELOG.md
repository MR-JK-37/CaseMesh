# Changelog

All notable changes to the CaseMesh repository are documented in this file.

## [Unreleased]

### Added
- **Rules Engine (`rules`)**:
  - Overlap level predicate helpers (`is_high_overlap`, `is_potential_overlap`, `is_info_overlap`).
  - Reason inspection and scoring utilities (`get_overlap_reason_codes`, `has_overlap_reason`, `calculate_time_proximity_score`, `get_shared_references`).
  - Institution candidate filtering and resolution helpers (`filter_candidates_by_min_score`, `is_resolution_matched`, `get_top_candidate`, `has_matching_permanent_id`).
  - Text normalization tokenization and Jaccard similarity calculators (`tokenize_normalized_text`, `calculate_token_jaccard`, `normalize_external_reference`).
  - Cross-bureau comparison predicate `is_cross_bureau_pair` and category utility `get_all_category_names`.
  - Test helper factory `create_case_facts` for reproducible testing.
- **UI Tokens (`@icm/ui-tokens`)**:
  - Typography letter spacing tokens (`tighter`, `tight`, `normal`, `wide`) and key types.
  - Shape specification z-index scale tokens (`base`, `card`, `header`, `dropdown`, `modal`, `toast`, `tooltip`).
  - Shape token accessors `getRadius` and `getElevation`.
  - Helper functions `isBrandToneKey` and `getStatusColor`.
- **UI Components (`@icm/ui-web`)**:
  - Exported standard props interfaces across `Card`, `Tile`, `GlassSurface`, `Icon`, `Gauge`, `BarChart`, `StatusBadge`, `Input`, `Table`, `Chip`, and `PillNav`.
  - Accessible `aria-label`, `aria-pressed`, and table caption attributes for keyboard and screen-reader navigation.
  - Safe theme token color references replacing raw color literals.
- **Backend Core & Models (`backend`)**:
  - Canonical constants and predicate helpers for `CASE_STATUSES`, `MATTER_TYPES`, `PRIORITIES`, `SOURCE_CHANNELS`, and `DISPOSAL_TYPES`.
  - Batch permission checks `can_any` and `can_all` in authorization policy.
  - Enhanced security helpers (`mask_email`, `truncate_for_log`, `is_argon2_hash`, `is_valid_uuid`, `generate_secure_random_string`).
- **Internationalization (`@icm/i18n`)**:
  - Common action and navigation translation keys across English (`en`), Hindi (`hi`), and Tamil (`ta`).
