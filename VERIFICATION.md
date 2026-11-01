# Verification

## Executed

- **33 Python tests passed, no skips**, using an existing Hermes Python runtime with FastAPI/HTTPX. Includes 29 service tests plus registration and HTTP adapter tests; automatic signed-in account/organization discovery and partial-discovery warnings are covered.
- **10 Desktop tests passed**, rendering through real React DOM, React Query and jsdom; SDK host primitives and backend responses are mocked. Covers automatic read-only project discovery, project search and selection across owners, the multiplexed-profile routing regression, all card kinds, select/drag status changes, issue editing, comments, close/reopen, creation, errors, scope changes, and composer/clipboard behavior.
- `node --check desktop/plugin.js` passed.
- `hermes plugins doctor . --ci` passed: eight tools registered.
- `hermes plugins validate . --json` passed all checks, with no warnings; security scan reported safe.
- **Live GitHub issue operations passed** against a temporary issue in this repository: read, update title/body and exact empty labels/assignees, comment, close and reopen. The temporary issue was deleted and absence verified.
- **Live GitHub Projects service operations passed** against a temporary private project owned by the authenticated account: list, read empty/populated board, create issue plus project attachment, and move a card to In Progress with persisted readback.
- A move using an incorrect null previous status was rejected. GitHub had automatically assigned Todo on attachment. Re-reading the card and moving with its actual status succeeded; the plugin did not overwrite stale state.
- The second temporary issue and test project were deleted; issue absence and project-list absence were verified.
- **Installed Desktop smoke:** enabled the agent plugin in the active profile, reloaded Desktop plugins, enabled its Desktop half through Capabilities, opened the GitHub Projects sidebar page, entered the owner and loaded the project selector. The initial empty state and compact top-aligned layout were visually inspected; no plugin-load error appeared.
- **404 investigation:** a live diagnostic showed the gateway socket profile was `default`, although the focused session belonged to the profile where the plugin was installed. The new regression failed with `default` versus the expected focused profile, then passed after explicit profile routing. The installed UI subsequently reached the correct backend instead of returning 404.
- **Automatic discovery:** the new service was executed live and returned the signed-in account's and organization projects, including the owner's existing project. No project or issue was modified during this read-only check.
- **Visual redesign:** replaced the project browser, board, cards, issue dialog and creation form styling. Re-ran all 33 Python tests and 10 rendered Desktop tests successfully; JavaScript syntax, plugin validation and `git diff --check` passed. Verified all referenced Hermes theme tokens exist in the installed Desktop stylesheet.
- **Redesigned installed UI:** reloaded Desktop plugins and cleared an intermediate hot-reload render error through Retry. Verified automatic project discovery, selected the existing `blprnt-ai` roadmap project, rendered its populated board, opened `blprnt-ai/blprnt #4` in the new issue dialog, and closed the dialog without saving. Inspected native dark-theme screenshots of the picker, board and editor. No GitHub writes were performed for the redesign.

## Limits

- Live discovery, populated-board selection and opening/closing an issue editor are now verified. Actual Desktop drag/drop, saving edits and composer insertion remain covered by rendered mocks, not live Desktop writes.
- The earlier 0.1.1 check encountered a cached Python router and the runtime refused an in-gateway restart; that restriction was not bypassed. The redesign check subsequently reached working discovery, board and issue endpoints through the installed UI. No backend restart was performed during the redesign.
- No exhaustive accessibility audit, narrow-window/theme matrix, remote-gateway test, or cross-account test was executed.
- Read-before-write timestamp/status checks are best-effort, not atomic GitHub concurrency guarantees.
- The source was installed locally via the active profile's plugin link. The app-level Desktop copy was created by Hermes' own reconciliation; other profile configurations were not edited.
- The active GitHub login initially lacked Projects scope. It was subsequently granted `project`; live Projects checks ran after the grant.

No CI workflows were added or run. No existing user issues/projects were edited; only explicitly named temporary fixtures in the new repository/test project were used.
