# Design-fidelity review — Phase 0

Per Section 9.11 point 5: compares the Phase 0 component gallery and sign-in
screen (`docs/ui-evidence/phase-0/*.png`) against `ui-refrence-iamge.png`.

## What matches

- **Backdrop gradient**: deep navy → mid blue radial gradient, same feel as
  the reference's phone-shell background. Verified pixel values from
  Section 9.2 used directly (`#032D45` → `#439BCD`).
- **Card surfaces**: white/soft-lavender cards on the blue field, 24px
  corner radius, soft shadow — matches the reference's room/device cards.
- **Semi-circular gauge with ticks**: directly modeled on the reference's
  "Climate Control" temperature gauge (arc, tick marks, gradient fill,
  center readout).
- **Vertical bar chart, one highlighted gradient bar + marker dot**: matches
  the reference's "Device Energy Usage" / monthly bar charts.
- **Chip filter row with outlined active chip**: matches "All / Living Room
  / Kitchen" row styling (pill shape, outlined inactive, filled active).
- **Status badges**: not in the reference (no equivalent concept), but use
  the same tint-background + saturated-text pattern as the reference's
  "ON"/device-state badges.
- **Typography feel**: bold navy headings, muted gray-blue secondary text,
  tabular numerals for big stat numbers — matches the reference's "1632kwh"
  / "24°C" treatment.

## Deliberate deviations (with reasons)

- **Text placement on the gradient**: the reference puts white text
  directly on the light-blue gradient end (~3.3:1, fails AA — Section 9.1
  rule 4 flags this explicitly). This build keeps the gradient look but
  never places body text on the light end uncomposited — text sits on
  solid/glass cards, or on `grad-text` (verified ≥4.5:1), never on raw
  `grad-deco`. Confirmed via axe-core (0 serious/critical violations) and
  the dedicated contrast script.
- **Pill navigation**: the reference's bottom nav expands the active item
  into a filled gradient *circle* with the label floating below/beside it.
  Phase 0's `PillNav` instead fills the active item's own pill with the
  gradient and keeps the label inline inside it — closer to a standard
  accessible tab pattern, same gradient-fill language. A closer circular
  expansion is a Phase 6/7 refinement candidate, not required for the
  Phase 0 gate.
- **No photography**: the reference uses room/device photos on cards.
  Section 9.2 explicitly forbids reusing the reference's imagery; Phase 0's
  institution cards (not yet built — that's Phase 2) are specified to use a
  monogram avatar on `grad-deco` instead.
- **Glass usage is more restrained**: the reference's cards themselves read
  as slightly translucent in places. Section 9.1 rule 3 is explicit that
  content cards stay solid and glass is reserved for the functional layer
  (nav, command bar, floating controls, dialogs) — Phase 0's `GlassSurface`
  is only used for the sign-in card chrome and the nav-style components,
  per that rule, not for dashboard content cards (`Card`/`Tile`, solid).

## What this review does not yet cover

Phase 0 only produced the component gallery and the sign-in shell — no
product screens exist yet (dashboard, cases table, institution profile,
etc.). A full side-by-side of real product screens against the reference
happens at the Phase 6 gate once those screens exist, per Section 9.11.
