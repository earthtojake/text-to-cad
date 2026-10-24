"""The logos' deliverables: a STEP of each, rewritten from its model on every run."""
from pathlib import Path

from cadgen import export

from logo_c import logo_c
from logo_cad import logo_cad
from logo_texttocad import logo_texttocad

ROOT = Path(__file__).resolve().parent.parent      # models/branding

if __name__ == "__main__":
    for logo in (logo_c, logo_cad, logo_texttocad):
        export(logo, ROOT / "STEP" / f"{logo.__name__}.step")
