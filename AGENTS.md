# AMFI SSD Downloader — Codex Instructions

## Goal

Build and maintain a Python downloader for AMFI Scheme Summary Documents.

Source page:

https://www.amfiindia.com/otherdata/scheme-details

For every AMC that AMFI returns:

1. Discover all schemes that AMFI returns.
2. Discover the Scheme Summary Document links for each scheme.
3. Download every available XML file.
4. Download every available XLS or XLSX file.
5. Download every available PDF file.
6. Store all files on the local filesystem.
7. Write one CSV report for each run.
8. Write one log file for each run.

## Current scope

The application must not:

- Use PostgreSQL.
- Use S3.
- Parse SSD contents.
- Extract SSD fields.
- Compare historical SSD contents.
- Hard-code AMC names.
- Hard-code scheme names.
- Guess download URLs.

## ASD-STE100 instruction handling

The upstream project is:

https://github.com/danyuchn/asd-ste100-skill

Install it into:

skills/asd-ste100/

If `skills/asd-ste100/SKILL.md` exists, use it for implementation requests that contain multiple requirements, conditions, or failure cases.

Before implementation:

1. Read the task for meaning.
2. Apply the ASD-STE100 clarity rules.
3. Preserve every technical requirement.
4. Preserve every condition.
5. Preserve every edge case.
6. Do not add requirements that the user did not request.
7. Use short and explicit working instructions.
8. State failure behavior explicitly.
9. Use the clarified specification as the working plan.
10. Then implement the task.

Do not apply STE rewriting to source code.

## Discovery rules

1. Use values that AMFI returns.
2. Do not maintain a manual AMC list.
3. Do not maintain a manual scheme list.
4. Do not construct SSD URLs from guesses.
5. Prefer verified direct HTTP endpoints if Codex discovers them.
6. Use Playwright when AMFI discovery depends on interactive browser behavior.
7. Keep AMFI-specific discovery logic in `src/amfi_ssd/discovery.py`.
8. Keep file downloading in `src/amfi_ssd/downloader.py`.

## Download rules

1. One AMC failure must not stop the run.
2. One scheme failure must not stop the run.
3. One missing document format must not stop the run.
4. Download to a `.part` file first.
5. Validate the `.part` file.
6. Rename the file only after validation succeeds.
7. Delete failed `.part` files.
8. If a valid target file already exists, skip it unless `--force` is set.
9. Save downloaded bytes without modifying them.

## File validation

XML:

- The file must have non-zero size.
- The file must not be HTML.
- The XML must be syntactically parseable.

PDF:

- The file must have non-zero size.
- The file must start with `%PDF`.

XLS/XLSX:

- The file must have non-zero size.
- The file must not be HTML.
- Do not rewrite the spreadsheet.

## Output structure

Use:

data/downloads/YYYY-MM-DD/
    AMC_NAME/
        SCHEME_ID_SCHEME_NAME/
            SSD.xml
            SSD.xls
            SSD.xlsx
            SSD.pdf

Reports:

data/reports/download_report_YYYY-MM-DD_HHMMSS.csv

Logs:

data/logs/download_YYYY-MM-DD_HHMMSS.log

## Format statuses

Use only:

- DOWNLOADED
- SKIPPED_EXISTING
- MISSING
- FAILED

## Scheme statuses

Use only:

- SUCCESS
- PARTIAL
- FAILED

## Testing

Before a full run:

1. Test one AMC.
2. Test two schemes.
3. Test all three document formats when available.
4. Run the same test twice.
5. Confirm the second run skips existing valid files.
6. Confirm one failed document does not stop the next scheme.

Do not run all AMCs until the small test passes.
