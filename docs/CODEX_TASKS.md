# Suggested Codex task sequence

## Task 1

Inspect the AMFI Scheme Details page.

Apply the ASD-STE100 guidance before implementation.

Do not change downloader logic.

Identify whether stable direct HTTP endpoints exist for:

- AMC discovery
- scheme discovery
- SSD-link discovery

Record verified findings in `docs/amfi_endpoints.md`.

Do not guess an endpoint.

## Task 2

Run:

```bash
python main.py --limit-amcs 1 --limit-schemes 2
```

Fix only discovery issues.

Do not add database code.

Do not parse downloaded SSD contents.

## Task 3

Test three different AMCs.

Verify:

- AMC discovery
- scheme discovery
- XML link discovery
- spreadsheet link discovery
- PDF link discovery

Fix only universal discovery problems.

## Task 4

Run the same sample twice.

Confirm valid existing files become `SKIPPED_EXISTING`.

## Task 5

Only after Tasks 1-4 pass, run the full AMC list.
