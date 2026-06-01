# Drive Access Mode (`DRIVE_ACCESS_MODE`)

This server supports two Drive scope/tool profiles, selectable at launch and
defaulting to the safe one. The mode governs only the **drive, sheets, slides,
and docs** tool groups. Gmail, Calendar, Chat, Forms, Tasks, Contacts,
Search/CSE, and Apps Script are unaffected and request identical scopes in both
modes.

## Selecting the mode

Resolution order (first match wins; unknown/empty fails closed to `file`):

1. `--drive-access-mode {file,full}` CLI flag
2. `DRIVE_ACCESS_MODE` env var
3. `WORKSPACE_MCP_DRIVE_ACCESS_MODE` env var
4. default → `file`

The platform sets this per launch based on the connection's OAuth mode:
platform-managed (shared) connections → `file`; BYO-OAuth connections → `full`.

| Behavior | `file` (default) | `full` |
|---|---|---|
| Drive-family resource scope | `drive.file` only | broad Drive scopes (see below) |
| Discovery tools registered | no | yes |
| ID-addressed read/write tools | yes | yes |
| `create_*` `parent_folder_id` | yes | yes |

Discovery tools gated off in `file` mode: `search_drive_files`,
`list_drive_items`, `search_docs`, `list_docs_in_folder`, `list_spreadsheets`.

## Hard invariant

The scope set the server requests on token refresh must **exactly equal** what
the OAuth grant authorized for that connection. A mismatch yields
`invalid_scope`. The platform's `packages/tool-registry/src/providers/gsuite.ts`
`suggestedScopes` must be made mode-conditional to match the lists below.

## Complete requested-scope sets

Computed from `auth.scopes.get_scopes_for_tools(...)` with **all** services
enabled (`gmail, drive, calendar, docs, sheets, chat, forms, slides, tasks,
contacts, search, appscript`). The only difference between the two modes is the
Drive-family resource scopes; every other scope is identical.

### `file` mode (27 scopes)

```
openid
https://www.googleapis.com/auth/userinfo.email
https://www.googleapis.com/auth/userinfo.profile
https://www.googleapis.com/auth/gmail.modify
https://www.googleapis.com/auth/gmail.settings.basic
https://www.googleapis.com/auth/calendar
https://www.googleapis.com/auth/chat.messages
https://www.googleapis.com/auth/chat.messages.readonly
https://www.googleapis.com/auth/chat.spaces
https://www.googleapis.com/auth/chat.spaces.readonly
https://www.googleapis.com/auth/contacts
https://www.googleapis.com/auth/contacts.readonly
https://www.googleapis.com/auth/cse
https://www.googleapis.com/auth/forms.body
https://www.googleapis.com/auth/forms.body.readonly
https://www.googleapis.com/auth/forms.responses.readonly
https://www.googleapis.com/auth/tasks
https://www.googleapis.com/auth/tasks.readonly
https://www.googleapis.com/auth/script.projects
https://www.googleapis.com/auth/script.projects.readonly
https://www.googleapis.com/auth/script.deployments
https://www.googleapis.com/auth/script.deployments.readonly
https://www.googleapis.com/auth/script.processes
https://www.googleapis.com/auth/script.metrics
https://www.googleapis.com/auth/script.external_request
https://www.googleapis.com/auth/script.scriptapp
https://www.googleapis.com/auth/drive.file
```

Drive-family contribution (`drive` + `docs` + `sheets` + `slides`):

```
https://www.googleapis.com/auth/drive.file
```

### `full` mode (35 scopes)

Same as `file` mode plus the 8 broad Drive-family resource scopes:

```
https://www.googleapis.com/auth/drive
https://www.googleapis.com/auth/drive.readonly
https://www.googleapis.com/auth/documents
https://www.googleapis.com/auth/documents.readonly
https://www.googleapis.com/auth/spreadsheets
https://www.googleapis.com/auth/spreadsheets.readonly
https://www.googleapis.com/auth/presentations
https://www.googleapis.com/auth/presentations.readonly
```

Drive-family contribution (`drive` + `docs` + `sheets` + `slides`):

```
https://www.googleapis.com/auth/drive
https://www.googleapis.com/auth/drive.readonly
https://www.googleapis.com/auth/drive.file
https://www.googleapis.com/auth/documents
https://www.googleapis.com/auth/documents.readonly
https://www.googleapis.com/auth/spreadsheets
https://www.googleapis.com/auth/spreadsheets.readonly
https://www.googleapis.com/auth/presentations
https://www.googleapis.com/auth/presentations.readonly
```

> If a deployment enables only a subset of services, intersect these lists with
> the enabled groups. The Drive-family difference above is the only part that
> changes between modes.

## Notes

- In `file` mode, `drive.file` is treated as the effective Drive-resource scope:
  the per-tool authorization check (`has_required_scopes`) accepts a `drive.file`
  grant for ID-addressed Drive/Docs/Sheets/Slides tools, which the Google APIs
  honor for app-created or user-picked files. In `full` mode this loosening is
  **not** applied — behavior is identical to before this change.
- Granular `--permissions` mode is a separate scope mechanism (BYO/self-hosted)
  and is not altered by `DRIVE_ACCESS_MODE` — scopes are requested verbatim from
  the permission entries. However, the discovery tools are still gated by
  `--drive-access-mode`: under `--permissions` with the default `file` mode they
  remain unregistered even if broad Drive scopes were granted. Operators who want
  the discovery tools must also pass `--drive-access-mode full`.
- `create_drive_folder`, `create_doc`, `create_presentation`, and `create_form`
  accept an optional `parent_folder_id` in both modes. For Docs/Slides/Forms the
  new file is placed via a follow-up Drive `files.update` (valid under
  `drive.file`); the Drive service for that move is acquired lazily, so creating
  in root still works when Drive access was not granted. `create_script_project`
  is intentionally **not** included — Apps Script's native `parentId` binds a
  script to a container document, not a folder, and the Apps Script group is out
  of scope for this change; it keeps its upstream `parent_id` parameter unchanged.
- Read-only + `file` mode + Apps Script: `appscript` is intentionally not a
  Drive-family group, so its read-only scope set still carries `drive.readonly`.
  In that specific combination the overall grant is therefore not purely
  `drive.file`. This is by design (Apps Script scopes are mode-invariant) and is
  not a refresh-invariant violation.
- The discovery-tool gate is evaluated at tool-module **import time**. Both
  entrypoints (`main.py`, `fastmcp_server.py`) resolve and set the mode before
  importing tool modules. Any future code path that imports a Drive-family tool
  module earlier would freeze the gate at `file` — keep mode resolution first.
