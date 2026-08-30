from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from amfi_ssd.utils import sanitize_filename


def test_sanitize_filename():
    assert sanitize_filename('A/B:C*D?E"F<G>H|I') == "A_B_C_D_E_F_G_H_I"


def test_sanitize_filename_spaces():
    assert sanitize_filename("  HDFC   Mutual Fund  ") == "HDFC_Mutual_Fund"
