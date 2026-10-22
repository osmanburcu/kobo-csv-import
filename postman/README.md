# Import a CSV into KoboToolbox with Postman

A manual alternative to the GitHub Action. Postman sends one submission to Kobo
for every row in a CSV file. The JSON is built from the CSV's own column names,
so any form works without editing the collection.

Use this for one-off imports you want to check by eye. Use the GitHub Action
(see the main [README](../README.md)) for automatic imports from SharePoint or Google Drive.

## Files

| File | What it is |
|---|---|
| `kobo-import.postman_collection.json` | The request, with a script that builds the JSON from each CSV row |
| `kobo.postman_environment.json` | Kobo URL, form UID and your API token |

## 1. Import into Postman

1. Open Postman → **Import** → select both JSON files in this folder.
2. Go to **Environments** → **Kobo** and fill in:

   | Variable | Value |
   |---|---|
   | `kobo_url` | `https://kf.kobotoolbox.org/{username}/submission?format=json`, with `{username}` replaced by your Kobo username. Preset to `https://kf.kobotoolbox.org/osmanburcu/submission?format=json` |
   | `asset_uid` | UID of the form receiving the data, e.g. `aNAmpcbU9opH9xA6NtbL3x` |
   | `kobo_token` | Your Kobo API token (Account settings → Security). Kept as a secret value |
   | `column_map` | Optional. Renames columns, see [Column names → JSON](#column-names--json). Default `{}` |
   | `skip_columns` | Optional. Comma-separated columns not to send, e.g. `start,end,deviceid` |

3. Select the **Kobo** environment in the top-right corner.

Never put the token in the collection itself or share the environment file once the token is filled in.

## 2. Prepare the CSV

- **Column names must be the XML names**, with groups separated by `/`, for example
  `geo/p1`. When exporting from Kobo, choose *XML values and headers* and group
  separator `/`. Names must match the questions of the form you import into
  (or be renamed with `column_map`).
- **Use commas as the separator.** Kobo exports often use `;`. Open the file in
  Excel and save it as *CSV (Comma delimited)*, or change the separator in the export settings.
- **Save as UTF-8** so letters such as ş, ğ, ı stay correct.
- **Keep the `_uuid` column.** It becomes the `instanceID`, so Kobo rejects a row
  that was already imported instead of creating a duplicate. Rows without `_uuid`
  (or `meta/instanceID`) get a new random ID.

## Column names → JSON

Every column becomes a field, and each `/` in its name becomes a level in the JSON:

| CSV column | Value | Sent as |
|---|---|---|
| `geo/p1` | Sahinbey | `"geo": { "p1": "Sahinbey" }` |
| `geo/p2` | *(empty)* | not sent, treated as unanswered |
| `compliance_summary/final_grp/calculation_001` | pH%206.8 | `"compliance_summary": { "final_grp": { "calculation_001": "pH 6.8" } }` |
| `_uuid` | 6b1f… | `"meta": { "instanceID": "uuid:6b1f…" }` |

Rules:

- Columns starting with `_` (`_id`, `_submission_time`, `_validation_status`, …),
  `formhub/…` and `meta/…` are Kobo metadata and are not sent as answers.
- Empty cells are left out.
- `%20` in a value is turned into a space.
- Columns listed in `skip_columns` are left out.

**Importing into a form with different names or groups:** set `column_map` to a JSON
object of `"CSV column": "target name"`. Columns not in the map keep their name.
For example, this is the mapping the original Power Automate flow used:

```json
{
  "context/ccp_id": "geo/ccp_id",
  "compliance_summary/final_grp/calculation_001": "geo/parameters"
}
```

Repeat groups cannot be imported this way. A Kobo CSV export puts them in separate
sheets or files, so only non-repeating questions are sent.

## 3. Run

1. Right-click the **Kobo CSV import** collection → **Run collection**.
2. Under **Data**, select your CSV file and click **Preview** to check the columns are read correctly.
3. Set **Delay** to `200` ms.
4. Turn on **Persist responses for a session** so you can open each row's reply from Kobo.
5. Click **Run Kobo CSV import**.

**Test first:** set **Iterations** to `1` to send just the first row, then check
the submission in Kobo before running the whole file.

## 4. Check the results

Each row appears as a test named `Row N: HTTP <code>`.

| Result | Meaning |
|---|---|
| `201` | Created |
| `202` + "duplicate" in the console | Already in Kobo (same `_uuid`), nothing changed |
| `400` | Bad data, e.g. a value that does not match the target form's question type |
| `401` / `403` | Wrong token, or your account cannot submit to this form |
| `404` | Wrong `kobo_url` or `asset_uid` |

Open **Console** (bottom bar) to see the exact request body and Kobo's reply for any row.

To see the exact JSON a row produces without sending it, open the request's
**Scripts → Pre-request** tab, add `console.log(pm.variables.get("payload"))` at the
end, and run with an invalid `kobo_url` such as `http://localhost:1`.

## Running without the Postman app (Newman)

The free Postman plan limits how many collection runs you get per month. To avoid the
limit, run the same files from the command line with [Newman](https://www.npmjs.com/package/newman):

```bash
npm install -g newman
```

```bash
newman run kobo-import.postman_collection.json -e kobo.postman_environment.json --env-var "kobo_token=YOUR_TOKEN" -d data.csv --delay-request 200
```
