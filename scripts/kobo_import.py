#!/usr/bin/env python3
"""Import a CSV into a KoboToolbox form.

Downloads a CSV (SharePoint, Google Drive or a file in the repo), fills a
JSON submission template for every row and POSTs each one to Kobo.

The template uses the same expressions as the Power Automate flow, e.g.
    "@{triggerBody()?['geo/p1']}"
    "@{replace(triggerBody()?['x'],'%20', ' ')}"
    "@{concat('uuid:', triggerBody()?['_uuid'])}"
where triggerBody() is the current CSV row (column name -> value).
A shorter "{{geo/p1}}" placeholder is also accepted.

Configuration comes from environment variables (see README.md).
"""

import base64
import copy
import csv
import io
import json
import os
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from urllib.parse import quote

import requests

# --------------------------------------------------------------------------
# Template expressions (small subset of the Power Automate / Logic Apps language)
# --------------------------------------------------------------------------

_TOKEN_RE = re.compile(
    r"\s*(?:(?P<str>'(?:[^']|'')*')"
    r"|(?P<num>-?\d+(?:\.\d+)?)"
    r"|(?P<name>[A-Za-z_][A-Za-z0-9_]*)"
    r"|(?P<op>[?\[\](),.]))"
)


def _s(value):
    """Convert a value the way string interpolation does (null -> '')."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


FUNCTIONS = {
    "replace": lambda s, old, new: _s(s).replace(_s(old), _s(new)),
    "concat": lambda *args: "".join(_s(a) for a in args),
    "coalesce": lambda *args: next((a for a in args if a is not None), None),
    "trim": lambda s: _s(s).strip(),
    "toLower": lambda s: _s(s).lower(),
    "toUpper": lambda s: _s(s).upper(),
    "string": _s,
    "guid": lambda: str(uuid.uuid4()),
    "utcNow": lambda *_: datetime.now(timezone.utc).isoformat(),
}


class Expression:
    def __init__(self, text, row):
        self.tokens = self._tokenize(text)
        self.pos = 0
        self.row = row

    @staticmethod
    def _tokenize(text):
        tokens, pos = [], 0
        text = text.rstrip()
        while pos < len(text):
            m = _TOKEN_RE.match(text, pos)
            if not m or m.end() == pos:
                raise ValueError(f"Cannot parse expression near: {text[pos:]!r}")
            kind = m.lastgroup
            tokens.append((kind, m.group(kind)))
            pos = m.end()
        return tokens

    def _peek(self):
        return self.tokens[self.pos] if self.pos < len(self.tokens) else (None, None)

    def _next(self):
        tok = self._peek()
        self.pos += 1
        return tok

    def _expect(self, op):
        kind, val = self._next()
        if kind != "op" or val != op:
            raise ValueError(f"Expected {op!r} but found {val!r}")

    def evaluate(self):
        value = self._expr()
        if self.pos != len(self.tokens):
            raise ValueError(f"Unexpected token {self._peek()[1]!r}")
        return value

    def _expr(self):
        kind, val = self._next()
        if kind == "str":
            value = val[1:-1].replace("''", "'")
        elif kind == "num":
            value = float(val) if "." in val else int(val)
        elif kind == "name":
            self._expect("(")
            args = []
            if self._peek() != ("op", ")"):
                args.append(self._expr())
                while self._peek() == ("op", ","):
                    self._next()
                    args.append(self._expr())
            self._expect(")")
            value = self._call(val, args)
        else:
            raise ValueError(f"Unexpected token {val!r}")

        # Property access: x?['key'], x['key'], x.key, x?.key
        while True:
            if self._peek() == ("op", "?"):
                self._next()
            if self._peek() == ("op", "["):
                self._next()
                key = self._expr()
                self._expect("]")
                value = value.get(_s(key)) if isinstance(value, dict) else None
            elif self._peek() == ("op", "."):
                self._next()
                _, key = self._next()
                value = value.get(key) if isinstance(value, dict) else None
            else:
                return value

    def _call(self, name, args):
        if name in ("triggerBody", "body", "item", "row"):
            return self.row
        if name not in FUNCTIONS:
            raise ValueError(f"Unsupported function {name}()")
        return FUNCTIONS[name](*args)


def render_string(text, row):
    """Replace every @{...} and {{column}} in a string."""
    out, i = [], 0
    while i < len(text):
        if text.startswith("@{", i):
            # find the closing brace that is not inside a quoted string
            j, in_quote = i + 2, False
            while j < len(text) and (in_quote or text[j] != "}"):
                if text[j] == "'":
                    in_quote = not in_quote
                j += 1
            if j >= len(text):
                raise ValueError(f"Unclosed @{{ in {text!r}")
            out.append(_s(Expression(text[i + 2 : j], row).evaluate()))
            i = j + 1
        elif text.startswith("{{", i) and "}}" in text[i:]:
            j = text.index("}}", i)
            out.append(_s(row.get(text[i + 2 : j].strip())))
            i = j + 2
        else:
            out.append(text[i])
            i += 1
    return "".join(out)


def render(node, row):
    if isinstance(node, dict):
        return {k: render(v, row) for k, v in node.items()}
    if isinstance(node, list):
        return [render(v, row) for v in node]
    if isinstance(node, str):
        return render_string(node, row)
    return node


# --------------------------------------------------------------------------
# CSV sources
# --------------------------------------------------------------------------

def download_sharepoint(file_ref):
    tenant = os.environ["MS_TENANT_ID"]
    token = requests.post(
        f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
        data={
            "client_id": os.environ["MS_CLIENT_ID"],
            "client_secret": os.environ["MS_CLIENT_SECRET"],
            "scope": "https://graph.microsoft.com/.default",
            "grant_type": "client_credentials",
        },
        timeout=30,
    )
    token.raise_for_status()
    headers = {"Authorization": f"Bearer {token.json()['access_token']}"}
    graph = "https://graph.microsoft.com/v1.0"

    if file_ref.startswith("http"):
        # Sharing link or full file URL -> /shares/u!<base64url>/driveItem
        encoded = base64.urlsafe_b64encode(file_ref.encode()).decode().rstrip("=")
        url = f"{graph}/shares/u!{encoded}/driveItem/content"
    else:
        # Path inside the site's default document library, e.g. "Imports/data.csv"
        site = os.environ.get("SHAREPOINT_SITE")
        if not site:
            raise SystemExit("SHAREPOINT_SITE is required when FILE is a path, "
                             "e.g. contoso.sharepoint.com:/sites/MEAL")
        r = requests.get(f"{graph}/sites/{site}", headers=headers, timeout=30)
        r.raise_for_status()
        site_id = r.json()["id"]
        url = f"{graph}/sites/{site_id}/drive/root:/{quote(file_ref.strip('/'))}:/content"

    r = requests.get(url, headers=headers, timeout=120)
    r.raise_for_status()
    return r.content


def download_gdrive(file_ref):
    from google.oauth2 import service_account
    from google.auth.transport.requests import Request

    m = re.search(r"/d/([\w-]+)|[?&]id=([\w-]+)", file_ref)
    file_id = (m.group(1) or m.group(2)) if m else file_ref.strip()

    creds = service_account.Credentials.from_service_account_info(
        json.loads(os.environ["GDRIVE_SERVICE_ACCOUNT_JSON"]),
        scopes=["https://www.googleapis.com/auth/drive.readonly"],
    )
    creds.refresh(Request())
    headers = {"Authorization": f"Bearer {creds.token}"}
    api = f"https://www.googleapis.com/drive/v3/files/{file_id}"

    meta = requests.get(api, headers=headers, timeout=30,
                        params={"fields": "mimeType,name", "supportsAllDrives": "true"})
    meta.raise_for_status()
    if meta.json()["mimeType"] == "application/vnd.google-apps.spreadsheet":
        # Native Google Sheet -> export first sheet as CSV
        r = requests.get(f"{api}/export", headers=headers, timeout=120,
                         params={"mimeType": "text/csv"})
    else:
        r = requests.get(api, headers=headers, timeout=120,
                         params={"alt": "media", "supportsAllDrives": "true"})
    r.raise_for_status()
    return r.content


def load_rows(raw):
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1252")
    try:
        dialect = csv.Sniffer().sniff(text[:10000], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    rows = []
    for row in csv.DictReader(io.StringIO(text), dialect=dialect):
        # Empty cells behave like missing answers (null) in Power Automate
        rows.append({k.strip(): (v if v != "" else None)
                     for k, v in row.items() if k is not None})
    return rows


# --------------------------------------------------------------------------
# Kobo
# --------------------------------------------------------------------------

def post_submission(session, url, payload, retries=3):
    for attempt in range(1, retries + 1):
        try:
            r = session.post(url, json=payload, timeout=60)
        except requests.RequestException as exc:
            if attempt == retries:
                return "failed", str(exc)
        else:
            if r.status_code == 429 or r.status_code >= 500:
                if attempt == retries:
                    return "failed", f"HTTP {r.status_code}: {r.text[:300]}"
            elif r.ok:
                status = "duplicate" if "duplicate" in r.text.lower() else "ok"
                return status, f"HTTP {r.status_code}"
            else:
                return "failed", f"HTTP {r.status_code}: {r.text[:300]}"
        time.sleep(2 ** attempt)


def main():
    source = os.environ.get("SOURCE", "repo").lower()
    file_ref = os.environ["FILE"]
    template_path = os.environ.get("TEMPLATE", "templates/submission.json")
    dry_run = os.environ.get("DRY_RUN", "false").lower() == "true"
    kobo_url = os.environ.get("KOBO_SUBMISSION_URL") or \
        "https://kc.kobotoolbox.org/api/v1/submissions"
    out_dir = os.environ.get("OUTPUT_DIR", "output")
    os.makedirs(out_dir, exist_ok=True)

    with open(template_path, encoding="utf-8") as f:
        template = json.load(f)
    if os.environ.get("ASSET_UID"):
        template["id"] = os.environ["ASSET_UID"]

    print(f"Downloading CSV from {source}: {file_ref}")
    if source == "sharepoint":
        raw = download_sharepoint(file_ref)
    elif source == "gdrive":
        raw = download_gdrive(file_ref)
    else:
        with open(file_ref, "rb") as f:
            raw = f.read()
    rows = load_rows(raw)
    print(f"Loaded {len(rows)} rows")

    session = requests.Session()
    if not dry_run:
        token = os.environ.get("KOBO_TOKEN")
        if not token:
            raise SystemExit("KOBO_TOKEN secret is not set")
        session.headers.update({"Authorization": f"Token {token}",
                                "Accept": "application/json"})

    results = []
    with open(os.path.join(out_dir, "payloads.jsonl"), "w", encoding="utf-8") as payloads:
        for n, row in enumerate(rows, start=1):
            try:
                payload = render(copy.deepcopy(template), row)
            except ValueError as exc:
                results.append((n, "", "failed", f"template error: {exc}"))
                continue

            # Kobo needs a unique instanceID; generate one if the CSV had no _uuid
            meta = payload.setdefault("submission", {}).setdefault("meta", {})
            if meta.get("instanceID", "") in ("", "uuid:"):
                meta["instanceID"] = f"uuid:{uuid.uuid4()}"
            instance_id = meta["instanceID"]
            payloads.write(json.dumps(payload, ensure_ascii=False) + "\n")

            if dry_run:
                if n <= 3:
                    print(json.dumps(payload, indent=2, ensure_ascii=False))
                results.append((n, instance_id, "dry-run", ""))
                continue

            status, message = post_submission(session, kobo_url, payload)
            print(f"Row {n}: {status} {message}")
            results.append((n, instance_id, status, message))
            time.sleep(0.2)

    with open(os.path.join(out_dir, "results.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["row", "instanceID", "status", "message"])
        w.writerows(results)

    counts = {}
    for _, _, status, _ in results:
        counts[status] = counts.get(status, 0) + 1
    summary = ", ".join(f"{k}: {v}" for k, v in sorted(counts.items())) or "no rows"
    print(f"Done. {summary}")

    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(f"### Kobo import\n\nSource: `{source}` `{file_ref}`\n\n"
                    f"| Status | Rows |\n|---|---|\n")
            for k, v in sorted(counts.items()):
                f.write(f"| {k} | {v} |\n")
            failed = [r for r in results if r[2] == "failed"]
            if failed:
                f.write("\n**Failed rows**\n\n| Row | Message |\n|---|---|\n")
                for r in failed[:50]:
                    f.write(f"| {r[0]} | {r[3].replace('|', '/')} |\n")

    if counts.get("failed"):
        sys.exit(1)


if __name__ == "__main__":
    main()
