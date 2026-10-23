# Kobo CSV Import app

A small desktop app that does the whole import without Postman:
pick a CSV, preview the JSON, and send every row to a KoboToolbox form.

It works like the Postman collection: each column name becomes a field
(`geo/p1` → `{"geo": {"p1": ...}}`), so it works with any form.

## Start

Needs **Python 3** (from [python.org](https://www.python.org/downloads/); on Windows
tick *Add Python to PATH* during setup). Nothing else needs to be installed.

- **Windows:** double-click `Kobo CSV Import.bat`
- **Any system:** `python kobo_import_app.py`

## Use

1. **CSV file:** click *Browse…* and choose the file. A preview opens straight away.
2. Check the settings:

   | Field | Value |
   |---|---|
   | Kobo URL | `https://kf.kobotoolbox.org/{username}/submission?format=json`, with your Kobo username. Preset to `osmanburcu` |
   | Form UID | UID of the form receiving the data, e.g. `aNAmpcbU9opH9xA6NtbL3x` |
   | API token | Your Kobo API token (Account settings → Security) |
   | Column map | Optional. Renames columns, e.g. `{"context/ccp_id": "geo/ccp_id"}`. Leave `{}` if names already match |
   | Skip columns | Optional. Comma-separated columns not to send, e.g. `start,end,deviceid` |
   | Delay between rows | Pause between rows in milliseconds. `200` is fine |

3. **Preview** lists which columns are sent, which are skipped, and the JSON for the first row.
4. **Send first row only** sends one row as a test. Check it in Kobo.
5. **Send to Kobo** sends all rows. Each row shows as OK (green), DUPLICATE (orange)
   or FAILED (red) with the reason. **Stop** halts after the current row.
6. **Save results…** saves a CSV with the outcome of every row.

The settings are remembered for next time, except the token, which you enter each time.

## CSV rules

- Column names must be the XML names with `/` between groups. When exporting from Kobo,
  choose *XML values and headers* and group separator `/`.
- `,`, `;` and tab separators all work. UTF-8 and Excel's Windows encoding both work.
- Empty cells are not sent. `%20` in a value becomes a space.
- Kobo metadata columns (`_id`, `_submission_time`, `formhub/…`, `meta/…`) are not sent as answers.
- `_uuid` (or `meta/instanceID`) is used as the submission ID, so importing the same file
  twice gives DUPLICATE instead of a copy. Rows without it get a new ID.
- Repeat groups are not supported.

## Common errors

| Message | Fix |
|---|---|
| `HTTP 401 (check the token)` | Wrong or old token |
| `HTTP 403` | Your account cannot submit to this form |
| `HTTP 404` | Wrong Kobo URL or Form UID |
| `HTTP 400` | A value does not fit the target form's question, e.g. text in a number question |
| `Could not reach Kobo` | No internet, a proxy/VPN blocking it, or a typo in the URL |

## Make a single .exe (optional)

To share the app with people who do not have Python:

```bash
pip install pyinstaller
```

```bash
pyinstaller --onefile --windowed --name "Kobo CSV Import" kobo_import_app.py
```

The program is created in `dist/Kobo CSV Import.exe`.
