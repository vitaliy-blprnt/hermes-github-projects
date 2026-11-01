# Verification

## Executed

- **31 Python tests passed, no skips**, using an existing Hermes Python runtime with FastAPI/HTTPX. Includes 27 service tests plus registration and HTTP adapter tests.
- **7 Desktop tests passed**, rendering through real React DOM, React Query and jsdom; SDK host primitives and backend responses are mocked. Covers all card kinds, select/drag status changes, issue editing, comments, close/reopen, creation, search, errors, gateway/profile changes, and composer/clipboard behavior.
- `node --check desktop/plugin.js` passed.
- `hermes plugins doctor . --ci` passed: eight tools registered.
- `hermes plugins validate . --json` passed all checks, with no warnings; security scan reported safe.
- **Live GitHub issue operations passed** against a temporary issue in this repository: read, update title/body and exact empty labels/assignees, comment, close and reopen. The temporary issue was deleted and absence verified.
- **Live GitHub Projects service operations passed** against a temporary private project owned by the authenticated account: list, read empty/populated board, create issue plus project attachment, and move a card to In Progress with persisted readback.
- A move using an incorrect null previous status was rejected. GitHub had automatically assigned Todo on attachment. Re-reading the card and moving with its actual status succeeded; the plugin did not overwrite stale state.
- The second temporary issue and test project were deleted; issue absence and project-list absence were verified.
- **Installed Desktop smoke:** enabled the agent plugin in the active profile, reloaded Desktop plugins, enabled its Desktop half through Capabilities, opened the GitHub Projects sidebar page, entered the owner and loaded the project selector. The initial empty state and compact top-aligned layout were visually inspected; no plugin-load error appeared.

## Limits

- The live Desktop smoke did not complete selection of the populated temporary project through the available computer-use bridge. Therefore real Desktop drag/drop, modal editing and composer insertion are **not** claimed as live-verified. Those paths have rendered mocked coverage; their shared GitHub service has live coverage.
- No exhaustive accessibility audit, narrow-window/theme matrix, remote-gateway test, or cross-account test was executed.
- Read-before-write timestamp/status checks are best-effort, not atomic GitHub concurrency guarantees.
- The source was installed locally via the active profile's plugin link. The app-level Desktop copy was created by Hermes' own reconciliation; other profile configurations were not edited.
- The active GitHub login initially lacked Projects scope. It was subsequently granted `project`; live Projects checks ran after the grant.

No CI workflows were added or run. No existing user issues/projects were edited; only explicitly named temporary fixtures in the new repository/test project were used.
