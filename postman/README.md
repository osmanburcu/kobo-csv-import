# Import a CSV into KoboToolbox with Postman

A manual alternative to the GitHub Action. Postman sends one submission to Kobo
for every row in a CSV file, using the same JSON structure as the Power Automate flow.

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
   | `kobo_url` | `https://kc.kobotoolbox.org/api/v1/submissions` (EU server: `https://kc-eu.kobotoolbox.org/api/v1/submissions`) |
   | `asset_uid` | UID of the form receiving the data, e.g. `aNAmpcbU9opH9xA6NtbL3x` |
   | `kobo_token` | Your Kobo API token (Account settings → Security). Kept as a secret value |

3. Select the **Kobo** environment in the top-right corner.

Never put the token in the collection itself or share the environment file once the token is filled in.

## 2. Prepare the CSV

- **Column names must be the XML names** of the source form, for example
  `geo/p1` or `context/ccp_id`. When exporting from Kobo, choose
  *XML values and headers* and group separator `/`.
- **Use commas as the separator.** Kobo exports often use `;`. Open the file in
  Excel and save it as *CSV (Comma delimited)*, or change the separator in the export settings.
- **Save as UTF-8** so letters such as ş, ğ, ı stay correct.
- **Keep the `_uuid` column.** It becomes the `instanceID`, so Kobo rejects a row
  that was already imported instead of creating a duplicate. Rows without `_uuid`
  get a new random ID.

Expected columns:

```
geo/p0_label, geo/p1, geo/p2, geo/p3, geo/system_id, context/ccp_id,
compliance_summary/final_grp/calculation_001, _uuid
```

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

## Changing the fields

The JSON is built in the request's **Scripts → Pre-request** tab. To add a field,
add a line inside `geo` (or a new group), reading the CSV column with `v("column/name")`:

```javascript
geo: {
  p1: v("geo/p1"),
  new_field: v("geo/new_field"),   // added
  ...
}
```

The keys on the left must match the target form's question names and groups.

## Running without the Postman app (Newman)

The free Postman plan limits how many collection runs you get per month. To avoid the
limit, run the same files from the command line with [Newman](https://www.npmjs.com/package/newman):

```bash
npm install -g newman
```

```bash
newman run kobo-import.postman_collection.json -e kobo.postman_environment.json --env-var "kobo_token=YOUR_TOKEN" -d data.csv --delay-request 200
```
