#!/usr/bin/env python3
"""Check the release manifest, extension descriptors, examples and ZIP payloads."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
NS = {"inx": "http://www.inkscape.org/namespace/inkscape/extension"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate(archives=None):
    packages = json.loads((ROOT / "tools/release_manifest.json").read_text())["packages"]
    version = (ROOT / "VERSION").read_text().strip()
    require(re.fullmatch(r"\d+\.\d+\.\d+", version), "Invalid suite version")
    ids, descriptors = set(), set()
    for package in packages:
        names = {Path(name).name for name in package["files"]}
        for name in package["files"] + [package["readme"]]:
            path = ROOT / name
            require(path.is_file(), f"Missing {name}")
            if path.suffix == ".inx":
                descriptors.add(path)
                tree = ET.parse(path)
                identifier = tree.findtext("inx:id", namespaces=NS)
                require(identifier and identifier not in ids, f"Duplicate or missing ID: {name}")
                ids.add(identifier)
                command = tree.find("inx:script/inx:command", NS)
                require(command is not None and command.text.strip() in names, f"Missing runtime: {name}")
        examples = [p for pattern in package["examples"] for p in ROOT.glob(pattern) if p.suffix == ".svg"]
        require(examples, f'No SVG examples: {package["name"]}')
        for example in examples:
            require(ET.parse(example).getroot().tag == "{http://www.w3.org/2000/svg}svg", f"Invalid SVG: {example}")
    expected = set(ROOT.glob("*.inx")) | set((ROOT / "modern_grid").glob("*.inx"))
    require(descriptors == expected, "Manifest does not cover every current extension descriptor")
    for document in [ROOT / "README.md", ROOT / "examples/README.md", *sorted((ROOT / "docs").glob("*.md"))]:
        for target in re.findall(r"\]\(([^)]+)\)", document.read_text()):
            if not target.startswith(("https://", "http://", "#")):
                require((document.parent / target.split("#")[0]).exists(), f"Broken link in {document.name}: {target}")
    print(f"Validated {len(packages)} extensions, {len(ids)} unique descriptors and their SVG examples")
    if archives:
        sums = {}
        for line in (archives / "SHA256SUMS").read_text().splitlines():
            digest, name = line.split("  ", 1)
            sums[name] = digest
        expected_names = {f'{p["name"]}-{p["version"]}.zip' for p in packages}
        expected_names |= {f"Binsalmarts-Extensions-{version}.zip", f"Binsalmarts-Examples-{version}.zip", "Studio-Dark-Compact-2.3.zip"}
        require(set(sums) == expected_names, "Missing or unexpected release archives")
        for name, digest in sums.items():
            path = archives / name
            require(hashlib.sha256(path.read_bytes()).hexdigest() == digest, f"Checksum mismatch: {name}")
            with zipfile.ZipFile(path) as archive:
                require(archive.testzip() is None, f"Corrupt archive: {name}")
                entries = archive.namelist()
                require(len(entries) == len(set(entries)), f"Duplicate archive paths: {name}")
                require(all(not p.startswith("/") and ".." not in Path(p).parts for p in entries), f"Unsafe archive path: {name}")
                require(all("__pycache__" not in p and ".DS_Store" not in p for p in entries), f"Cache in {name}")
        with zipfile.ZipFile(archives / f"Binsalmarts-Extensions-{version}.zip") as archive:
            for package in packages:
                for source in package["files"]:
                    member = package["name"] + "/" + Path(source).name
                    require(archive.read(member) == (ROOT / source).read_bytes(), f"Stale runtime: {member}")
        with zipfile.ZipFile(archives / "Studio-Dark-Compact-2.3.zip") as archive:
            prefix = "Studio-Dark-Compact/"
            require(prefix + "theme/gtk-3.0/vendor/mactahoe/COPYING" in archive.namelist(), "Missing upstream theme license")
            require((archive.getinfo(prefix + "install-macos.command").external_attr >> 16) & 0o111, "Installer is not executable")
        print(f"Validated all {len(sums)} release ZIPs, runtime contents, theme license and SHA-256 checksums")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archives", type=Path)
    validate(parser.parse_args().archives)
