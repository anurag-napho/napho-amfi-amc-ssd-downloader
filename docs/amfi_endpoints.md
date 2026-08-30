# AMFI endpoint notes

Source page:

https://www.amfiindia.com/otherdata/scheme-details

Verified on 2026-08-30:

- Scheme endpoint: `GET https://www.amfiindia.com/api/populate-scheme`
- Scheme parameter: `MF_ID=<AMC ID>`
- Scheme response: A JSON list with `scheme_id` and `scheme_name`.
- Document endpoint: `GET https://www.amfiindia.com/api/schemes/<scheme ID>/documents`
- Document response: A JSON object with a `data` list.
- SSD fields: `summaryXmlUrl`, `summaryXlsUrl`, and `summaryPdfUrl`.

Each run requests the scheme endpoint for each AMC. It requests the document
endpoint for each scheme. It does not construct document URLs.

If a direct endpoint fails or returns an incompatible response, Playwright uses
the AMFI Scheme Details page. The fallback reads scheme and document responses
from the browser interaction.
