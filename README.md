# AMFI SSD Downloader

This Python application downloads Scheme Summary Documents from AMFI.

Source page:

<https://www.amfiindia.com/otherdata/scheme-details>

The application downloads these available formats:

- XML
- XLS or XLSX
- PDF

The application stores the original files on the local filesystem. It does not
change or parse the file contents.

The application does not use PostgreSQL or S3.

## How it works

```mermaid
flowchart LR
    A[Get AMCs] --> B[Get schemes]
    B --> C[Get fresh SSD URLs]
    C --> D[Check each URL]
    D --> E[Download or skip files]
    E --> F[Write report and log]
```

For each run, the application does these steps:

1. It gets the current AMC list from AMFI.
2. It gets the current scheme list for each AMC.
3. It gets fresh SSD URLs for each scheme.
4. It checks each available URL with a streamed `GET` request.
5. It downloads new files to temporary `.part` files.
6. It validates each `.part` file.
7. It renames each valid `.part` file to its final name.
8. It writes one CSV report and one log file.

If direct HTTP discovery fails, Playwright uses the AMFI Scheme Details page.

## Requirements

- Python 3.10 or newer
- Internet access
- Git, only if you want to install the ASD-STE100 skill

## Setup on macOS or Linux

Run these commands from the project directory.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m playwright install chromium
```

## Setup on Windows PowerShell

Run these commands from the project directory.

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m playwright install chromium
```

If PowerShell blocks activation, use this command for the current terminal:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

Then activate the environment again.

## Run a small test first

Process one AMC and two schemes:

```bash
python main.py --limit-amcs 1 --limit-schemes 2
```

Run the same command a second time:

```bash
python main.py --limit-amcs 1 --limit-schemes 2
```

The second run still checks every available URL. It marks valid local files as
`SKIPPED_EXISTING`.

## Run one named AMC

Process all schemes for an AMC whose name contains the specified text:

```bash
python main.py --amc "HDFC Mutual Fund"
```

Process only five schemes from that AMC:

```bash
python main.py --amc "HDFC Mutual Fund" --limit-schemes 5
```

The AMC match is not case-sensitive. The text can match part of an AMC name.

## Run all AMCs

Run this command only after the small test succeeds:

```bash
python main.py
```

## Download files again

Use `--force` to replace existing valid files:

```bash
python main.py --limit-amcs 1 --limit-schemes 2 --force
```

The application still checks each URL before it replaces a file.

## Show detailed log messages

Use `--verbose` to show HTTP request details:

```bash
python main.py --limit-amcs 1 --limit-schemes 2 --verbose
```

## Show the fallback browser

Normal discovery does not open a browser window. Use `--headed` to show the
browser if Playwright fallback starts:

```bash
python main.py --limit-amcs 1 --limit-schemes 2 --headed
```

## Use a different download directory

Use `--output-dir` to set the download root:

```bash
python main.py --limit-amcs 1 --limit-schemes 2 --output-dir my-downloads
```

Reports and logs still use the standard `data` directories.

## Show all command options

```bash
python main.py --help
```

## Download process

The application processes XML, XLS/XLSX, and PDF separately.

1. A missing AMFI URL gets the `MISSING` status.
2. An available URL receives a streamed `GET` request.
3. A non-200 response gets the `FAILED` status.
4. A valid local file gets the `SKIPPED_EXISTING` status.
5. A new response is written to a `.part` file.
6. An invalid `.part` file is deleted.
7. A valid `.part` file gets its final name and `DOWNLOADED` status.

One file failure does not stop the next file. One scheme failure does not stop
the next scheme.

## Validation rules

### XML

- The file must not be empty.
- The file must not contain HTML.
- The XML syntax must be valid.

### PDF

- The file must not be empty.
- The file must start with `%PDF`.

### XLS or XLSX

- The file must not be empty.
- The file must not contain HTML.
- The application does not rewrite the spreadsheet.

## File statuses

- `DOWNLOADED`: The application downloaded and validated the file.
- `SKIPPED_EXISTING`: The URL worked and a valid local file existed.
- `MISSING`: AMFI did not return a URL for the format.
- `FAILED`: The URL check or file validation failed.

## Scheme statuses

- `SUCCESS`: All available files downloaded or already existed.
- `PARTIAL`: At least one file succeeded and at least one file failed.
- `FAILED`: No file succeeded.

Missing formats do not cause `PARTIAL` when all available files succeed.

## Output directories

Downloaded files use this structure:

```text
data/downloads/YYYY-MM-DD/
    AMC_NAME/
        SCHEME_ID_SCHEME_NAME/
            SSD.xml
            SSD.xls
            SSD.xlsx
            SSD.pdf
```

AMFI can omit one or more formats. The scheme directory contains only the files
that AMFI returned and the application downloaded.

Reports use this path:

```text
data/reports/download_report_YYYY-MM-DD_HHMMSS.csv
```

Logs use this path:

```text
data/logs/download_YYYY-MM-DD_HHMMSS.log
```

The CSV report contains one row for each processed scheme. The `Failure Details`
column contains the file name and failure reason.

Example:

```text
SSD.xml: Invalid XML | SSD.pdf: HTTP 404
```

## Run the automated tests

Install pytest if it is not available:

```bash
python -m pip install pytest
```

Run all tests:

```bash
python -m pytest -q
```

## Developer scripts

These scripts help investigate changes to the AMFI website. The downloader does
not use them during a normal run.

Open the AMFI page and inspect its inputs and buttons:

```bash
python debug.py
```

This script also writes `amfi_scheme_details_debug.png` in the project directory.

Open the AMFI page and print relevant browser requests:

```bash
python debug_network.py
```

Interact with the browser window. Return to the terminal and press Enter to stop
the script.

## Install the ASD-STE100 skill

This skill gives Codex writing instructions. The downloader does not require the
skill at runtime.

On macOS or Linux:

```bash
bash scripts/install_skill.sh
```

On Windows PowerShell:

```powershell
Remove-Item -Recurse -Force skills/asd-ste100
git clone https://github.com/danyuchn/asd-ste100-skill skills/asd-ste100
```

The install script replaces the existing `skills/asd-ste100` directory.

## Common problems

### Playwright cannot find Chromium

Run:

```bash
python -m playwright install chromium
```

### A URL returns HTTP 404 or HTTP 500

The application marks that file as `FAILED`. It records the reason in the CSV
report and log. It then continues with the next file.

### A downloaded file contains HTML

AMFI can return an error page instead of a document. The application rejects the
file and deletes its `.part` file.

### A local file is invalid

The application downloads a replacement after the URL check succeeds.

### An AMC name does not match

Use a shorter part of the AMC name. You can also run a one-AMC test without the
`--amc` option.
