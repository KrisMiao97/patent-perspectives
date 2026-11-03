"""Build the licensed skill and a clearly labelled synthetic offline demo."""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "patent-perspectives"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    if out.exists() and any(out.iterdir()):
        raise ValueError("Use a new or empty release output directory")
    if out.is_relative_to(SKILL):
        raise ValueError("Release output must be outside the skill")
    out.mkdir(parents=True, exist_ok=True)
    spec = importlib.util.spec_from_file_location("release_engine", SKILL / "scripts/patent_perspectives.py")
    engine = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(engine)
    archive = out / ("patent-perspectives_" + engine.SKILL_RELEASE + ".zip")
    engine.package_skill(archive)
    with zipfile.ZipFile(archive) as package:
        assert package.testzip() is None
        assert package.read("patent-perspectives/LICENSE") == (ROOT / "LICENSE").read_bytes()
        assert "patent-perspectives/README.md" in package.namelist()
    with tempfile.TemporaryDirectory(prefix="patent-release-demo-") as temporary:
        demo = Path(temporary) / "demo"
        subprocess.run([sys.executable, "-B", str(ROOT / "examples/synthetic-optics/generate_demo.py"),
                        "--output", str(demo)], cwd=ROOT, check=True)
        demo_archive = out / "patent-perspectives_synthetic-demo.zip"
        with zipfile.ZipFile(demo_archive, "w", compression=zipfile.ZIP_DEFLATED) as package:
            for path in sorted((demo / "report").rglob("*")):
                if path.is_file():
                    package.write(path, "synthetic-demo/" + path.relative_to(demo / "report").as_posix())
            package.write(ROOT / "LICENSE", "synthetic-demo/LICENSE")
            package.writestr("synthetic-demo/DEMO-NOTICE.txt", "SYNTHETIC software demonstration only. Review records are fixed test fixtures; no real patent or independent semantic review is claimed. Open index.html offline.\n")
    checksums = "".join(hashlib.sha256(path.read_bytes()).hexdigest() + "  " + path.name + "\n"
                        for path in sorted(out.glob("*.zip")))
    (out / "SHA256SUMS.txt").write_text(checksums, encoding="utf-8")
    (out / "release-tag.txt").write_text("v" + engine.SKILL_RELEASE, encoding="utf-8")
    print(json.dumps({"release": engine.SKILL_RELEASE, "files": sorted(p.name for p in out.iterdir())}))


if __name__ == "__main__":
    main()
