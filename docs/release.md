# Release Process

This document describes the steps to publish a new release of `DetectMateService`.

## Prerequisites

Before starting a release, make sure all work intended for this version has been merged into the `development` branch and that CI is passing.

## Steps

### 1. Merge Dependabot PRs into main

Review any open Dependabot pull requests and merge the relevant ones into `main` before continuing.

### 2. Merge development into main

Open a pull request to merge the `development` branch into `main`. Once CI passes and the PR is approved, merge it.

!!! note

    Merging `development` into `main` will delete the `development` branch. See the last step for how to recreate it.

### 3. Determine the new version number

`DetectMateService` follows [Semantic Versioning](https://semver.org/) (`MAJOR.MINOR.PATCH`):

- **Patch** (`0.3.x`): backwards-compatible bug fixes and small improvements.
- **Minor** (`0.x.0`): new backwards-compatible functionality. Reset the patch number to `0`.
- **Major** (`x.0.0`): incompatible API changes. Reset both minor and patch numbers to `0`.

### 4. Bump the version number

Create a new branch from `main` and update the version string in `src/service/metadata.py`:

```python
__version__ = '0.X.Y'  # set to the new release version
```

The version here must match the tag you will create in step 5 (e.g. version `0.4.0` corresponds to tag `v0.4.0`).

Also make sure `uv.lock` is up to date:

```bash
uv lock
```

Commit any changes, push the branch, and open a pull request against `main`. Once CI passes, merge it.

### 5. Create a GitHub release

Go to the [Releases page](https://github.com/ait-detectmate/DetectMateService/releases) and click **Draft a new release**.

- Set the tag to `vX.Y.Z` (e.g. `v0.4.0`), targeting the `main` branch. GitHub will create the tag on publish.
- Set the release title to the version string (e.g. `v0.4.0`).
- Click **Generate release notes** to populate the changelog automatically.
- Review the generated release notes and adjust if needed.
- Click **Publish release**.

### 6. Check automatically triggered workflows

Publishing the release triggers the following GitHub Actions workflows automatically:

- **Publish Docs** (`publish-docs.yml`): deploys a new versioned copy of the documentation and updates the `latest` alias.
- **Docker image** (`docker.yml`): builds and pushes a new Docker image to the GitHub Container Registry (`ghcr.io`).
- **PyPI package release**: publishes the new package version to PyPI.

Monitor the [Actions tab](https://github.com/ait-detectmate/DetectMateService/actions) to confirm all workflows complete successfully.

### 7. Recreate the development branch

Because merging `development` into `main` deletes the `development` branch, create a new one branching from the now-updated `main`:

```bash
git checkout main
git pull
git checkout -b development
git push -u origin development
```

The `development` branch is now ready for the next iteration of work.
