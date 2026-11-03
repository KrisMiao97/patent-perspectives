"""Run portable repository checks without external Python dependencies."""
from pathlib import Path
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
TEMP_ROOT = ROOT / "work" / ".test-tmp"


def run(*args):
    TEMP_ROOT.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    environment.update(TEMP=str(TEMP_ROOT), TMP=str(TEMP_ROOT), TMPDIR=str(TEMP_ROOT))
    subprocess.run(list(map(str, args)), cwd=ROOT, env=environment, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--node", default=shutil.which("node"))
    args = parser.parse_args()
    run(sys.executable, "-B", "-m", "unittest", "discover", "-s", "patent-perspectives/tests")
    run(sys.executable, "-B", "patent-perspectives/scripts/check_package.py")
    errors = []
    for path in ROOT.rglob("*.md"):
        if any(part in path.relative_to(ROOT).parts for part in ("work", "dist", ".git", "__pycache__")):
            continue
        for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
            target = target.strip("<>").split("#")[0]
            if not target or re.match(r"^[a-z]+:", target, re.I):
                continue
            destination = (path.parent / target).resolve()
            if not destination.is_relative_to(ROOT) or not destination.exists():
                errors.append(str(path.relative_to(ROOT)) + ": " + target)
    if errors:
        raise ValueError("Broken repository links: " + "; ".join(errors))
    assert (ROOT / "LICENSE").read_bytes() == (ROOT / "patent-perspectives/LICENSE").read_bytes()
    if not args.node:
        raise ValueError("Node.js is required for development JS syntax checks; use --node PATH")
    for path in (ROOT / "patent-perspectives/assets/panorama").glob("*.js"):
        run(args.node, "--check", path)
    with tempfile.TemporaryDirectory(prefix="publication-", dir=TEMP_ROOT) as temporary:
        run(sys.executable, "-B", "examples/synthetic-optics/generate_demo.py", "--output", Path(temporary) / "demo")
        run(sys.executable, "-B", "tools/build_release.py", "--output", Path(temporary) / "dist")
    print(json.dumps({"repository_checks": "passed", "synthetic_demo": "passed", "licenses_match": True}))


if __name__ == "__main__":
    main()
