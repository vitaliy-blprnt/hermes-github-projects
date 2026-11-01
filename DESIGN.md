# Desktop design

The GitHub Projects plugin is an operating surface inside Hermes, not a separate dashboard brand. GitHub remains authoritative; the visual redesign does not introduce new provider operations or automation.

## Direction

Use a restrained, compact project workspace: clear title hierarchy, fine separators, quiet metadata, consistent outline icons, and accent reserved for the primary action and status cues. Inherit Hermes fonts and semantic theme variables; do not hardcode a competing palette or add font/icon dependencies.

## Surfaces

- **Project browser:** searchable project rows with title, owner, project number, and a directional affordance. Keep the alternate-owner form secondary and collapsed. Show discovery errors and partial-access warnings without hiding usable projects.
- **Board:** breadcrumbs, project title, a primary New issue action, compact search/refresh controls, and horizontally scrollable fixed-width status columns. Cards distinguish repository identity, title, labels, assignees, editing, and status selection. Keep unknown and absent statuses visible; absent-status columns remain view-only.
- **Issue editor:** native modal with a persistent header, labeled fields, paired metadata, separate save/state/work actions, and a discussion section. Preparing work never submits chat.
- **Creation:** matching inline form with explicit repository, content, labels, and assignees. No automatic creation or submission.

## Interaction and sizing

Use native buttons and inputs, accessible names for icon-only controls, visible keyboard focus, and reduced-motion support. Adapt toolbar and paired fields to narrow containers; board columns retain readable width and scroll horizontally. Preserve explicit actions, stale-write guards, pending states, full backend errors, and connection/profile isolation.

## Verification boundary

See `VERIFICATION.md` for executed checks. Theme-token availability and passing DOM tests are not a complete contrast audit or a narrow-window visual matrix.
