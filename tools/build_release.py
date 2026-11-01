#!/usr/bin/env python3
"""Build deterministic installation ZIPs, examples and SHA256SUMS without Inkex."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def write_zip(path, files):
    if not files:
        raise ValueError(f"Empty archive: {path.name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, source in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = (0o100755 if source.suffix == ".command" else 0o100644) << 16
            archive.writestr(info, source.read_bytes())
    with zipfile.ZipFile(path) as archive:
        if archive.testzip() is not None:
            raise ValueError(f"Corrupt archive: {path.name}")
    print(path.name)


def package_files(package):
    prefix = package["name"] + "/"
    files = {prefix + Path(name).name: ROOT / name for name in package["files"]}
    files[prefix + "README.md"] = ROOT / package["readme"]
    files[prefix + "LICENSE"] = ROOT / "LICENSE"
    for pattern in package["examples"]:
        paths = sorted(ROOT.glob(pattern))
        if not paths:
            raise ValueError(f"Missing examples: {pattern}")
        for source in paths:
            files[prefix + source.relative_to(ROOT).as_posix()] = source
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist/release")
    args = parser.parse_args()
    version = (ROOT / "VERSION").read_text().strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("VERSION must be MAJOR.MINOR.PATCH")
    packages = json.loads((ROOT / "tools/release_manifest.json").read_text())["packages"]
    output = args.output.resolve()
    suite = {"README.md": ROOT / "README.md", "INSTALLATION.md": ROOT / "docs/INSTALLATION.md",
             "LICENSE": ROOT / "LICENSE"}
    products = []
    for package in packages:
        files = package_files(package)
        path = output / f'{package["name"]}-{package["version"]}.zip'
        write_zip(path, files)
        products.append(path)
        suite.update(files)
    path = output / f"Binsalmarts-Extensions-{version}.zip"
    write_zip(path, suite)
    products.append(path)

    # The theme uses a separate installer and keeps all third-party license files.
    theme = ROOT / "studio_dark"
    files = {}
    for name in ("install.py", "install-macos.command", "uninstall-macos.command", "README_AR.md",
                 "LICENSE", "THIRD_PARTY.md", "qa/QA.md", "qa/source-audit.json"):
        files["Studio-Dark-Compact/" + name] = theme / name
    for directory in ("theme", "examples"):
        for source in sorted((theme / directory).rglob("*")):
            if source.is_file() and source.name != ".DS_Store":
                files["Studio-Dark-Compact/" + source.relative_to(theme).as_posix()] = source
    path = output / "Studio-Dark-Compact-2.3.zip"
    write_zip(path, files)
    products.append(path)

    files = {"examples/README.md": ROOT / "examples/README.md",
             "studio_dark/examples/Studio-Dark.svg": ROOT / "studio_dark/examples/Studio-Dark.svg"}
    for name, source in suite.items():
        if "/examples/" in name:
            files[source.relative_to(ROOT).as_posix()] = source
    path = output / f"Binsalmarts-Examples-{version}.zip"
    write_zip(path, files)
    products.append(path)
    sums = "".join(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n"
                   for path in sorted(products))
    (output / "SHA256SUMS").write_text(sums, encoding="utf-8")
    print(f"{len(products)} archives verified; SHA256SUMS written to {output}")


if __name__ == "__main__":
    main()
