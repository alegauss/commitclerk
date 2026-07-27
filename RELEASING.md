# Releasing commitclerk

Publishing is automated by [`.github/workflows/publish.yml`](.github/workflows/publish.yml)
and uses **PyPI Trusted Publishing (OIDC)**. No API token is stored in this
repository — PyPI verifies the identity of the workflow itself, so there is no
long-lived secret to leak or rotate.

## One-time setup

Do this once, before the first release. It cannot be automated.

### 1. Create the pending publisher on PyPI

The project does not exist on PyPI yet, so register a *pending* publisher:

<https://pypi.org/manage/account/publishing/>

Fill in **exactly** these values:

| Field | Value |
|---|---|
| PyPI Project Name | `commitclerk` |
| Owner | `alegauss` |
| Repository name | `commitclerk` |
| Workflow name | `publish.yml` |
| Environment name | `pypi` |

### 2. Do the same on TestPyPI

<https://test.pypi.org/manage/account/publishing/> — identical values, except:

| Field | Value |
|---|---|
| Environment name | `testpypi` |

### 3. Create the GitHub environments

In **Settings → Environments**, create two environments named `pypi` and
`testpypi`. The names must match the workflow and the publisher configuration.

For `pypi`, adding yourself as a **required reviewer** is recommended: it means
every upload to the real index pauses for a manual approval click, which is a
cheap safety net against an accidental or malicious release.

## Cutting a release

1. **Bump the version.** Edit `__version__` in [`commitclerk.py`](commitclerk.py).
   That single value is the source of truth — `pyproject.toml` reads it
   dynamically, and CI fails the release if the git tag disagrees with it.

2. **Update the changelog.** Move everything under `## [Unreleased]` in
   [`CHANGELOG.md`](CHANGELOG.md) into a new `## [X.Y.Z] - YYYY-MM-DD` section,
   and update the link definitions at the bottom.

3. **Commit and push.**

   ```bash
   git add commitclerk.py CHANGELOG.md
   clerk -m "chore: release vX.Y.Z"
   git push
   ```

4. **Rehearse on TestPyPI** (optional but recommended for the first few
   releases). Run the *Publish* workflow manually from the Actions tab — a
   manual run always targets TestPyPI, never PyPI. Then verify:

   ```bash
   pipx install --index-url https://test.pypi.org/simple/ commitclerk
   clerk --version
   ```

5. **Tag and release.**

   ```bash
   git tag -a vX.Y.Z -m "vX.Y.Z"
   git push origin vX.Y.Z
   gh release create vX.Y.Z --generate-notes
   ```

   Publishing the GitHub Release triggers the workflow, which builds the sdist
   and wheel, checks the tag against `__version__`, and uploads to PyPI.

6. **Verify.**

   ```bash
   pipx install commitclerk
   clerk --version
   ```

## Versioning

[Semantic Versioning](https://semver.org/). For a CLI, that means:

- **major** — a flag or environment variable is removed or changes meaning, or
  the default behaviour changes in a way that surprises an existing user.
- **minor** — a new flag, a new provider, a new capability.
- **patch** — bug fixes, prompt tuning, documentation.

Changing the *generated commit message* through prompt tuning is a `patch` or
`minor`, never a `major` — the output is inherently non-deterministic and is not
part of the compatibility contract.

## If a release goes wrong

PyPI does not allow re-uploading a version, even after deletion. Yank the bad
release and ship a new patch version:

```bash
# On pypi.org: Manage project -> Releases -> Yank
```

Yanking hides the version from new installs while leaving it resolvable for
anyone who pinned it exactly — this is almost always better than deleting.
