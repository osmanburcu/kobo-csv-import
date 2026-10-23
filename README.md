# CSV → KoboToolbox import (GitHub Action)

Downloads a CSV from SharePoint, Google Drive or this repo, fills
`templates/submission.json` for each row and POSTs it to KoboToolbox,
the same way the Power Automate flow does.

```
.github/workflows/kobo-import.yml   the workflow
scripts/kobo_import.py              download, fill template, post
templates/submission.json           submission structure (Power Automate syntax works)
samples/sample.csv                  test data for a dry run
postman/                            manual alternative with Postman (see postman/README.md)
app/                                desktop app for manual imports (see app/README.md)
```

## Template

Keep the structure from Power Automate. `triggerBody()` means "the current CSV row",
so `triggerBody()?['geo/p1']` reads the `geo/p1` column.

Supported: `triggerBody()` / `body()`, `?['col']`, `replace`, `concat`, `coalesce`,
`trim`, `toLower`, `toUpper`, `string`, `guid()`, `utcNow()`.
A short form `"{{geo/p1}}"` also works.

Empty cells are treated as missing answers (become `""`). If a row has no `_uuid`,
a new `meta/instanceID` is generated.

**CSV columns must be the XML names**, e.g. `geo/p1`. When exporting from Kobo choose
*XML values and headers* and group separator `/`. Keep the `_uuid` column: Kobo
rejects a second submission with the same instanceID, so re-running the same file
will not create duplicates (they show as `duplicate` in the results).

## Setup

Repository → Settings → Secrets and variables → Actions.

| Name | Type | Needed for | Value |
|---|---|---|---|
| `KOBO_TOKEN` | secret | always | Kobo API token (Account settings → Security) |
| `KOBO_SUBMISSION_URL` | variable | optional | Default `https://kc.kobotoolbox.org/api/v1/submissions` (EU server: `https://kc-eu.kobotoolbox.org/api/v1/submissions`), or the URL your Power Automate flow already uses |
| `MS_TENANT_ID` | secret | SharePoint | Entra ID tenant ID |
| `MS_CLIENT_ID` | secret | SharePoint | App registration client ID |
| `MS_CLIENT_SECRET` | secret | SharePoint | App registration secret |
| `SHAREPOINT_SITE` | variable | SharePoint, when `file` is a path | `contoso.sharepoint.com:/sites/MEAL` |
| `GDRIVE_SERVICE_ACCOUNT_JSON` | secret | Google Drive | Full service-account key JSON |

**SharePoint:** create an app registration in Entra ID, add the Microsoft Graph
*application* permission `Sites.Read.All` (or `Sites.Selected` and grant the site),
admin-consent it, and create a client secret. `file` can be a sharing link or a path
in the site's Documents library such as `Imports/data.csv`.

**Google Drive:** create a service account in Google Cloud, enable the Drive API,
download a JSON key, and share the CSV (or its folder) with the service account's
email. `file` can be the file ID or its link. Native Google Sheets are exported as CSV.

## Run

- **By hand:** Actions → *Import CSV into KoboToolbox* → Run workflow. Tick *dry run*
  first to check the generated JSON (shown in the log and in the `kobo-import-results`
  artifact).
- **From Power Automate** (e.g. "When a file is created in a folder" → HTTP):

  ```
  POST https://api.github.com/repos/<owner>/<repo>/dispatches
  Authorization: Bearer <fine-grained PAT with Contents: read & write>
  Accept: application/vnd.github+json

  {"event_type": "kobo-import",
   "client_payload": {"source": "sharepoint", "file": "Imports/data.csv"}}
  ```

Each run uploads `output/results.csv` (row, instanceID, status, message) and
`output/payloads.jsonl`. The job fails if any row failed.

## Local test

```bash
pip install -r requirements.txt
SOURCE=repo FILE=samples/sample.csv DRY_RUN=true python scripts/kobo_import.py
```
