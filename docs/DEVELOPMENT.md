# Development and releases

## Run the tests

Use Python with Inkex from Inkscape 1.4+, Pillow and pypdf. On Ubuntu, install Inkscape from its [official stable PPA](https://wiki.inkscape.org/wiki/Installing_Inkscape), plus `python3-pil python3-pypdf python3-lxml python3-numpy python3-scipy python3-cssselect python3-serial python3-packaging`.

```bash
python3 tests/run_tests.py \
  --inkex-dir /usr/share/inkscape/extensions \
  --inkscape /usr/bin/inkscape
python3 -m unittest discover -s studio_dark/qa -p 'test_*.py' -v
python3 tools/validate_repository.py
```

On macOS, use `--inkex-dir /Applications/Inkscape.app/Contents/Resources/share/inkscape/extensions`, `--extra-packages /Applications/Inkscape.app/Contents/Resources/lib/python3.10/site-packages` and `--inkscape /Applications/Inkscape.app/Contents/MacOS/inkscape` with a working Python environment. The extra-packages directory depends on the installed Inkscape bundle.

`--pattern test_blend_tool_pro.py` runs one extension suite. Renderer tests are skipped when `--inkscape` is omitted. Theme installer tests use temporary profiles.

## Generate examples

Each `tools/make_*examples.py` script accepts `--inkex-dir` and `--extra-packages`. `tools/make_grid_examples.py` generates the Modern Grid examples. Existing SVG sources and results are committed, so generating them is optional for building a release.

## Build downloads

```bash
python3 tools/build_release.py
python3 tools/validate_repository.py --archives dist/release
```

The build uses only Python's standard library. It creates eight individual extension ZIPs, the complete extension ZIP, the separate theme ZIP, the examples ZIP and `SHA256SUMS`. ZIP entries use fixed timestamps and permissions for repeatable builds. Runtime paths are portable; diagnostic logs, personal installation records, caches and previous builds stay out of Git.

The extension list and component versions live in `tools/release_manifest.json`. `VERSION` is the suite release version, independent of component versions. Update both documentation and the manifest when changing a component version.

## Publish

1. Update `VERSION`, `CHANGELOG.md` and `docs/RELEASE_NOTES.md`.
2. Merge changes to `main` after CI passes.
3. A change to `VERSION` on `main` automatically starts publication. Alternatively, push a tag matching `VERSION`, for example `v1.0.0`.
4. The release workflow tests the exact commit, builds the packages and publishes the GitHub Release with all assets and checksums. It creates the version tag if necessary.

The release workflow also supports manual dispatch with a matching tag. It leaves an existing release unchanged. CI uses read-only repository permissions; publishing grants `contents: write` only to the release job. See the official [checkout](https://github.com/actions/checkout), [artifact upload](https://github.com/actions/upload-artifact), and [GitHub CLI release](https://cli.github.com/manual/gh_release_create) documentation.
