# Releasing Shelfpass

Releases are fully automated from git tags. Maintainers only bump the version, update the changelog and push a tag.

## Version numbers

- **App version:** [Semantic Versioning](https://semver.org/), `MAJOR.MINOR.PATCH`, in
  `shelfpass/__init__.py`.
  - `PATCH`: bug fixes and security fixes only.
  - `MINOR`: new features and new migrations that apply automatically.
  - `MAJOR`: anything operators must act on (settings renamed, manual data steps).
  - Pre-releases look like `1.1.0-rc.1`. They are published as GitHub pre-releases and never tagged `latest`.
- **Build number:** the number of commits in the built revision (`git rev-list --count HEAD`).
  CI and the release workflow pass it into the image as `BUILD_NUMBER`. The UI, `/version.json` and
  `/healthz` show it.
- **Dataset version:** `YYYY.MM.N` in `dataset/dataset.json`. Bump it when the dataset changes in a release.

## Cutting a release

1. Make sure `main` is green.
2. In one commit on `main`:
   - set `__version__` in `shelfpass/__init__.py`,
   - move the **Unreleased** notes in `CHANGELOG.md` under a new `## [X.Y.Z] - YYYY-MM-DD`
     heading and update the compare links at the bottom,
   - bump `dataset/dataset.json` if the dataset changed.
3. Check the version is consistent:
   ```bash
   python scripts/check_version.py vX.Y.Z
   ```
4. Tag and push:
   ```bash
   git tag -a vX.Y.Z -m "Shelfpass vX.Y.Z"
   git push origin main vX.Y.Z
   ```

The [Release workflow](../.github/workflows/release.yml) then:

1. fails fast if the tag, `__version__` and changelog disagree,
2. runs the whole CI pipeline against the tag,
3. builds the wheel, sdist and `shelfpass-dataset-<version>.zip`,
4. builds and pushes `ghcr.io/lobojoel2003/shelfpass` for `linux/amd64` and `linux/arm64`, tagged
   `X.Y.Z`, `X.Y`, `X`, `latest` and `build-N`, with a signed build-provenance attestation,
5. creates the GitHub Release with the changelog section as notes, an install snippet, build
   metadata and `SHA256SUMS.txt`.

You can also publish without pushing a tag yourself. Open **Actions → Release → Run workflow**, choose `main` and enter the tag (for example `v1.0.0`). If the tag doesn't exist yet, the workflow creates it as an annotated tag on that commit after checking it against `__version__` and the changelog, then carries on as above. If the tag already exists, the release is re-published and its assets are replaced in place.

## Verifying an image

```bash
gh attestation verify oci://ghcr.io/lobojoel2003/shelfpass:X.Y.Z --owner lobojoel2003
docker run --rm ghcr.io/lobojoel2003/shelfpass:X.Y.Z cat /app/BUILD_INFO.json
```
