"""Fetch RobStride's own STEP models of Galatea's five drives into vendor/, and convert each to an xbf.

    cad run src/vendor.py                 clone RobStride's repository at the commit named here, and take the five files
    cad run src/vendor.py CHECKOUT        take them from a checkout of it already on this computer

Run it once, before anything else here: `lib/hardware.py` reads vendor/RS04.xbf and its four
fellows, and no model builds without them. The files are RobStride's, 53 MB of them, and
Git keeps no CAD file, so they are fetched and not committed: vendor/ is ignored.

The repository is https://github.com/RobStride/Product_Information. Each file is checked
against the checksum it had when `lib/dims.py`'s numbers were measured on it (where its
mounting face lies, how it is turned, its envelope): a file RobStride has since revised is
still taken, and named, so that those numbers can be measured again.
"""

import hashlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPOSITORY = "https://github.com/RobStride/Product_Information"
COMMIT = "d739e98128afb8371dd177400c44ad54682ece23"            # 2026-11-09
VENDOR = Path(__file__).resolve().parents[1] / "vendor"
# model: (its folder under "Product Literature/CAN2.0", the file's sha256 when dims.py was measured on it)
FILES = {
    "RS00": ("RS00", "161ddbd84d04e7fa2731b0fb9a656e1c3a16cbcaba605d93f8805373cfc2c8c0"),
    "RS03": ("RS03", "405507c7c2abde1f5b5c0e3a40aab4f921d67c3b34506573524a624b07571301"),
    "RS04": ("RS04", "75cd1185a3a2bb265f6571ea47705ed891c75dfdaa51426deb940566fae504c9"),
    "RS05": ("RS05", "f802784facf23a1fb819d5d37f396c8369c851d5c10dda598566594117c588b1"),
    "RS06": ("RS06", "ed0c0517d9714ff9087cd675708e260b39f5e5e32523e10b3e2ebcbf7bf84cd1"),
}


def clone(into):
    """RobStride's repository at COMMIT, without its history."""
    run = lambda *words: subprocess.run(words, check=True, cwd=into, env={**__import__("os").environ, "GIT_LFS_SKIP_SMUDGE": "1"})
    run("git", "init", "--quiet")
    run("git", "remote", "add", "origin", REPOSITORY)
    try:
        run("git", "fetch", "--quiet", "--depth", "1", "origin", COMMIT)
    except subprocess.CalledProcessError:
        print(f"the commit {COMMIT[:10]} could not be fetched by name; taking the repository's newest", flush=True)
        run("git", "fetch", "--quiet", "--depth", "1", "origin")
    run("git", "checkout", "--quiet", "FETCH_HEAD")


def newest(folder, model):
    """The model's STEP file in its folder: the newest by the date in its name."""
    found = sorted(path for path in folder.iterdir() if path.suffix.lower() in (".stp", ".step") and path.name.upper().startswith(model))
    if not found:
        raise SystemExit(f"no STEP file for the {model} in {folder}")
    return found[-1]


def main(arguments):
    VENDOR.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as scratch:
        if arguments:
            checkout = Path(arguments[0]).expanduser().resolve()
        else:
            checkout = Path(scratch)
            print(f"cloning {REPOSITORY} (about 500 MB) ...", flush=True)
            clone(checkout)
        revised = []
        for model, (folder, checksum) in FILES.items():
            source = newest(checkout / "Product Literature" / "CAN2.0" / folder, model)
            step, converted = VENDOR / f"{model}.stp", VENDOR / f"{model}.xbf"
            shutil.copyfile(source, step)
            if hashlib.sha256(step.read_bytes()).hexdigest() != checksum:
                revised.append(f"{model} ({source.name})")
            subprocess.run(["cad", "step", "export", str(step), str(converted)], check=True)
            print(f"{model}: {source.name} -> {converted.relative_to(VENDOR.parent)}", flush=True)
    if revised:
        print("RobStride has revised " + ", ".join(revised) + " since lib/dims.py's numbers were measured on them: "
              "check each model's `step`, `flange`, `pins` and envelope there against the new file.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
