# Hermes GitHub Projects

A native Hermes Desktop Kanban board backed by GitHub Projects, with matching agent tools and a companion skill. GitHub owns the tasks; the plugin does not maintain a second board database or dispatch agents automatically.

## Features

- Choose a user/organization project and use its existing **Status** options as columns.
- View issues, pull requests, drafts and cards without a status; search the board.
- Move cards with drag-and-drop or an accessible status control.
- Create/edit issues, labels and assignees; read/post comments; close/reopen issues.
- Prepare a **Work on this** request without automatically running an agent.
- Use the same backend from chat via eight `github_projects_*` tools.

PR/draft editing and project administration stay in GitHub. Moving a card and closing an issue are separate operations; GitHub's own automations still apply.

## Requirements

- Hermes Desktop with the native unified plugin SDK (`ctx.rest`, sidebar routes, React Query) and Python plugin support. Developed against Hermes 0.22.5's installed SDK.
- GitHub CLI (`gh`) installed on the **gateway host** and authenticated to github.com.
- Projects scopes: `read:project` for viewing, `project` for changes, plus access to the relevant repositories. For a classic OAuth login:

```sh
gh auth status
gh auth refresh --hostname github.com --scopes project
```

This may open an interactive GitHub authorization flow. Do not put tokens in plugin settings. On a remote gateway, the remote login—not the viewing desktop's login—is used.

## Install

```sh
hermes plugins install vitaliy-blprnt/hermes-github-projects --enable
hermes plugins doctor github-projects --ci
```

Enable **GitHub Projects** in Hermes Desktop's Plugins settings too. The Python plugin and Desktop UI have separate enablement gates. If your running gateway does not pick up the new plugin, restart it at a safe point. The sidebar opens the board; enter a GitHub user or organization and choose a project. No GitHub Projects are created automatically.

For a local development checkout, clone this repository into a new directory, then link it as `$HERMES_HOME/plugins/github-projects` and run `hermes plugins enable github-projects`. Never replace an existing plugin directory without inspecting it first. Use the actual profile's `HERMES_HOME`, not another profile's directory.

## Chat workflow

The bundled skill is registered as `github-projects:github-projects`. Examples:

- “Show the projects owned by my-org.”
- “Show the blocked issues in my-org project 4.”
- “Create this issue in my-org/repo and add it to project 4.”
- “Move this card to In progress.”
- “Work on my-org/repo issue 12 in this checkout.”

Execution requires an explicit instruction. The skill does not grant permission to publish code or close issues automatically.

## Architecture and safety

`desktop/plugin.js` → authenticated Hermes plugin API → `github_projects.py` → GitHub CLI/API.
Agent tools in `__init__.py` call the same service. `dashboard/manifest.json` registers only the shared backend; there is no web-dashboard UI.

- No direct token handling, new credential store, local task database, or inbound webhook listener.
- Fixed operations and argument validation; no arbitrary shell execution.
- Pagination is followed rather than presenting a truncated board as complete.
- Edits compare the last-read update timestamp; moves compare the last-read status. These are best-effort stale-write checks, **not GitHub-wide atomic locks**.
- Writes are read back; failures after a possible write require reconciliation, not automatic retries.
- Labels/assignees in an edit replace the supplied collection; omit fields you do not intend to change.
- Issue text is rendered as text, not executable HTML.
- GitHub permissions remain authoritative. The plugin has the gateway account's access and is not a multi-user authorization layer.

## Development

No additional production Python or JavaScript packages are needed beyond Hermes' own runtime and `gh`.

```sh
python3 -m unittest discover -s tests -p 'test_*.py' -v
node --test tests/desktop.test.mjs
node --check desktop/plugin.js
hermes plugins doctor . --ci
hermes plugins validate . --json
```

Adapter tests require Hermes' Python environment (FastAPI, Pydantic and HTTPX); core service tests use only the standard library. Mocked tests do not prove live GitHub access or that Desktop loaded the UI. See [verification](VERIFICATION.md) for the actual tested scope and remaining gates.

## Out of scope

Web dashboard, stakeholder portal, repository-only boards, GitHub Enterprise, custom authentication, automatic agent dispatch, offline editing, and project/field administration.

## License

MIT.
