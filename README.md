# esgvoc_registry

This repository is the **release index** for [esgvoc](https://github.com/ESGF/esgf-vocab) pre-built database snapshots.

`esgvoc` uses this registry to discover, download, and verify versioned SQLite databases for each CV project. Every time you run `esgvoc use cmip7@1.1.0` or ,`esgvoc use cmip7@latest` esgvoc fetches the relevant JSON file from this repo to resolve the download URL and checksum.

---

## Structure

Each CV project has a single JSON index file at the root of this repository:

```
universe.json       # WCRP Universe shared vocabulary
cmip7.json          # CMIP7 Controlled Vocabularies
cmip6.json
cmip6plus.json
input4mips.json
obs4ref.json
cordex-cmip5.json
cordex-cmip6.json
emd.json
```

### Index file schema

```json
{
  "project_id": "cmip7",
  "releases": [
    {
      "version": "1.1.0",
      "tag": "cmip7.1.1.0",
      "url": "https://github.com/WCRP-CMIP/esgvoc_registry/releases/download/cmip7.1.1.0/cmip7-1.1.0.db",
      "checksum_sha256": "...",
      "size_bytes": 6381568,
      "is_prerelease": false,
      "published_at": "2026-05-12T09:59:27Z",
      "universe_version": "1.0.2"
    }
  ]
}
```

| Field | Description |
|-------|-------------|
| `version` | Bare semver (`1.1.0`). Special values: `dev-latest`. |
| `tag` | GitHub Release tag: `{project_id}.{version}` |
| `url` | Direct download URL for the `.db` asset |
| `checksum_sha256` | SHA-256 of the `.db` file, verified on download |
| `size_bytes` | File size in bytes |
| `is_prerelease` | `true` for `dev-latest` and release candidates |
| `published_at` | ISO 8601 UTC timestamp |
| `universe_version` | Version of WCRP-universe embedded in this snapshot |

Releases are listed newest-first. `esgvoc` resolves `latest` to the first non-prerelease entry.

---

## Versioning convention

Versions follow bare [SemVer](https://semver.org/) — **no `v` prefix**:

| Change | Bump | Example |
|--------|------|---------|
| New terms added to existing collections | patch | `1.0.1` → `1.0.2` |
| New collections added, or spec changes (catalog, attr…) | minor | `1.0.2` → `1.1.0` |
| Breaking structural changes | major | `1.1.0` → `2.0.0` |

> **Rule of thumb:** one merge of `esgvoc_dev` into `esgvoc` in a CV repository triggers one snapshot publication.

Note: releases `v1.0.0` predate this convention and carry a `v` prefix — all subsequent releases use bare semver.

---

## Publishing a new snapshot

Snapshots are built and published via the [`Publish DB`](.github/workflows/publish.yml) GitHub Actions workflow, triggered manually.

### Prerequisites

The CV repository must contain an `esgvoc_manifest.yaml` at its root:

```yaml
schema_version: "1"
project:
  id: "cmip7"
  name: "CMIP7 Controlled Vocabulary"
cv_version: "1.1.0"
universe_version: "1.0.2"
esgvoc:
  min_version: "4.0.0"
release_notes: |
  - fix(catalog_spec): replace organisation with institution
  - Added new experiment definitions
```

This manifest is read by `esgvoc admin build` during the CI build. The `release_notes` field is embedded in the database's `_esgvoc_metadata` table.

### Workflow inputs

#### Universe snapshot

| Input | Value |
|-------|-------|
| `project_id` | `universe` |
| `cv_version` | e.g. `1.0.2` |
| `universe_version` | same as `cv_version` |
| `universe_repo` | `WCRP-CMIP/WCRP-universe` |
| `universe_ref` | `esgvoc` |
| `is_prerelease` | `false` |

#### Project snapshot (e.g. cmip7)

| Input | Value |
|-------|-------|
| `project_id` | `cmip7` |
| `cv_version` | e.g. `1.1.0` |
| `universe_version` | version of universe embedded, e.g. `1.0.2` |
| `project_repo` | `WCRP-CMIP/CMIP7_CVs` |
| `project_ref` | `esgvoc` |
| `universe_repo` | `WCRP-CMIP/WCRP-universe` |
| `universe_ref` | `esgvoc` |
| `is_prerelease` | `false` |

> Always publish `universe` before any project that embeds it.

### Triggering via `gh` CLI

```bash
# Universe
gh workflow run publish.yml \
  --field project_id=universe \
  --field cv_version=1.0.2 \
  --field universe_version=1.0.2 \
  --field universe_ref=esgvoc \
  --field is_prerelease=false

# Project
gh workflow run publish.yml \
  --field project_id=cmip7 \
  --field cv_version=1.1.0 \
  --field universe_version=1.0.2 \
  --field project_repo=WCRP-CMIP/CMIP7_CVs \
  --field project_ref=esgvoc \
  --field universe_ref=esgvoc \
  --field is_prerelease=false
```

### What the workflow does

1. **Build** — clones both CV and universe repos at the given refs, runs `esgvoc admin build` (or `build-universe` for universe-only), producing a `.db` file with embedded metadata including `release_notes`
2. **Validate** — runs `esgvoc admin validate` on the resulting `.db`
3. **Publish** — creates (or replaces) a GitHub Release tagged `{project_id}.{version}` and uploads the `.db` asset
4. **Index** — prepends a new entry to `{project_id}.json` and commits it to `main`

### Testing before publishing

Use `esgvoc test run` to validate a branch end-to-end before triggering the workflow:

```bash
# Test cmip7 esgvoc branch against esgvoc_dev universe
esgvoc test run cmip7 --branch esgvoc --universe-branch esgvoc_dev

# Test universe branch standalone
esgvoc test run universe --branch esgvoc
```

Or build a local snapshot for manual inspection:

```bash
esgvoc admin build-universe \
  --universe-repo WCRP-CMIP/WCRP-universe \
  --universe-ref esgvoc \
  --universe-version 1.0.2 \
  --output /tmp/universe-1.0.2.db

esgvoc admin build \
  --project-repo WCRP-CMIP/CMIP7_CVs \
  --project-ref esgvoc \
  --universe-repo WCRP-CMIP/WCRP-universe \
  --universe-ref esgvoc \
  --output /tmp/cmip7-1.1.0.db
```

---

## Available projects

| Project ID | CV Repository | Description |
|------------|--------------|-------------|
| `universe` | [WCRP-CMIP/WCRP-universe](https://github.com/WCRP-CMIP/WCRP-universe) | Shared WCRP universe vocabulary |
| `cmip7` | [WCRP-CMIP/CMIP7_CVs](https://github.com/WCRP-CMIP/CMIP7_CVs) | CMIP7 controlled vocabularies |
| `cmip6` | WCRP-CMIP/CMIP6_CVs | CMIP6 controlled vocabularies |
| `cmip6plus` | WCRP-CMIP/CMIP6Plus_CVs | CMIP6Plus controlled vocabularies |
| `input4mips` | WCRP-CMIP/input4MIPs_CVs | Input4MIPs controlled vocabularies |
| `obs4ref` | WCRP-CMIP/obs4MIPs_CVs | Obs4MIPs reference vocabularies |
| `cordex-cmip5` | WCRP-CMIP/CORDEX_CVs | CORDEX-CMIP5 controlled vocabularies |
| `cordex-cmip6` | WCRP-CMIP/CORDEX-CMIP6_CVs | CORDEX-CMIP6 controlled vocabularies |
| `emd` | — | EMD (Essential Model Documentation controlled vocabularies) |

---

## Related repositories

- [ESGF/esgf-vocab](https://github.com/ESGF/esgf-vocab) — the esgvoc Python library that consumes this registry
- [WCRP-CMIP/WCRP-universe](https://github.com/WCRP-CMIP/WCRP-universe) — source of the shared universe vocabulary
- [WCRP-CMIP/CMIP7_CVs](https://github.com/WCRP-CMIP/CMIP7_CVs) — source of the CMIP7 CVs
