from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import main  # noqa: E402


def test_workers_default_is_four():
    assert main.parse_args([]).workers == 4


@pytest.mark.parametrize("workers", ["1", "16"])
def test_workers_accepts_safe_limits(workers):
    assert main.parse_args(["--workers", workers]).workers == int(workers)


@pytest.mark.parametrize("workers", ["0", "17", "not-a-number"])
def test_workers_rejects_values_outside_safe_limits(workers):
    with pytest.raises(SystemExit):
        main.parse_args(["--workers", workers])
