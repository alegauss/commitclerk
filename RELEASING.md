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

Both environments already exist: `pypi` and `testpypi`. Their names must keep
matching the workflow and the publisher configuration.

For `pypi`, adding yourself as a **required reviewer** (Settings → Environments
→ pypi) is worth considering: every upload to the real index would then pause
for one approval click. It is a cheap safety net against an accidental release,
at the cost of the automated path no longer being fully hands-off.

## Cutting a release

Nobody types a version number. Every run of the *Publish* workflow computes the
next one from `__version__` in [`commitclerk.py`](commitclerk.py), which is the
single source of truth — `pyproject.toml` reads it dynamically.

**1. Write the changelog.** Add what changed under `## [Unreleased]` in
[`CHANGELOG.md`](CHANGELOG.md). This is the only manual step; the workflow moves
that section into a released one for you. If you leave it empty the release
still goes out, marked as a maintenance release.

**2. Rehearse on TestPyPI** (optional). Actions → *Publish* → *Run workflow*,
leaving `target` on **testpypi**. It builds `X.Y.(Z+1).devN` — a throwaway
version so TestPyPI never rejects a duplicate — and commits and tags nothing.
Verify with:

```bash
pipx install --index-url https://test.pypi.org/simple/ commitclerk
clerk --version
```

**3. Release.** Actions → *Publish* → *Run workflow*, set `target` to **pypi**
and pick `level` (**patch** by default; `minor` for a new flag or provider,
`major` for a breaking change). The run then, in order:

1. bumps `__version__` and rolls `CHANGELOG.md`,
2. commits `chore: release vX.Y.Z`, tags `vX.Y.Z` and pushes both,
3. builds the sdist and wheel and validates them with `twine check`,
4. uploads to PyPI via OIDC,
5. creates the GitHub Release with generated notes.

**4. Verify.**

```bash
pipx install commitclerk
clerk --version
```

### Releasing a specific tag by hand

The automated path is the normal one, but publishing a GitHub Release manually
still works and uploads exactly that tag. The workflow then refuses to run if
the tag and `__version__` disagree, so bump the module first:

```bash
git tag -a vX.Y.Z -m "vX.Y.Z"
git push origin vX.Y.Z
gh release create vX.Y.Z --generate-notes
```

### Why the GitHub Release is created last

It is created with the built-in `GITHUB_TOKEN`. Releases published by that token
deliberately do not trigger workflows, which is what keeps `publish.yml` from
re-entering itself. Creating it after the upload also means a failed upload does
not leave a release announcing a version that never reached PyPI.

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
