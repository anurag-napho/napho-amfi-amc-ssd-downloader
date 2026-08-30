from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from amfi_ssd.logging_setup import configure_logging
from amfi_ssd.runner import run_downloader


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download AMFI Scheme Summary Documents."
    )
    parser.add_argument(
        "--output-dir",
        default="data/downloads",
        help="Root local download directory.",
    )
    parser.add_argument(
        "--amc",
        default=None,
        help="Process only AMCs whose name contains this text.",
    )
    parser.add_argument("--limit-amcs", type=int, default=None)
    parser.add_argument("--limit-schemes", type=int, default=None)
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Deprecated compatibility option. HTTP discovery does not use it.",
    )
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")

    report_file = ROOT / "data" / "reports" / f"download_report_{stamp}.csv"
    log_file = ROOT / "data" / "logs" / f"download_{stamp}.log"
    output_dir = (ROOT / args.output_dir).resolve()

    configure_logging(log_file, verbose=args.verbose)

    totals = run_downloader(
        output_dir=output_dir,
        report_file=report_file,
        headed=args.headed,
        force=args.force,
        amc_filter=args.amc,
        limit_amcs=args.limit_amcs,
        limit_schemes=args.limit_schemes,
    )

    print()
    print("Run complete")
    print("------------")
    print(f"AMCs discovered:    {totals['amcs_discovered']}")
    print(f"AMCs processed:     {totals['amcs_processed']}")
    print(f"Schemes discovered: {totals['schemes_discovered']}")
    print(f"Schemes processed:  {totals['schemes_processed']}")
    print(f"SUCCESS:            {totals['success']}")
    print(f"PARTIAL:            {totals['partial']}")
    print(f"FAILED:             {totals['failed']}")
    print(f"Report:             {report_file}")
    print(f"Log:                {log_file}")


if __name__ == "__main__":
    main()
