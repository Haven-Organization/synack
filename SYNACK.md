# Maintaining SynACK

SynACK is stock Synapse plus a small set of patches. This document describes
how those patches are tracked and how new upstream releases are merged.

## Layout

- `main` contains the complete upstream Synapse history, with the SynACK
  commits on top. Upstream commits keep their original authors.
- Upstream is the `upstream` remote, `https://github.com/element-hq/synapse.git`.
  SynACK follows upstream release tags (`v1.x.y`), not `develop`.
- `.synack/UPSTREAM_BASE` records the last unmodified upstream release that
  was merged (tag and commit). It is the reference point for everything below.

Files that exist only in SynACK: `README.md`, `SYNACK.md`, `.synack/`,
`scripts-dev/synack-sync-upstream.sh`, and a block at the end of `.gitignore`.

`.github/dependabot.yml` is deleted in SynACK. Dependency updates arrive
through upstream release merges, so the fork does not take separate Dependabot
pull requests. If upstream changes that file, the merge reports a
modify/delete conflict; resolve it by keeping the file deleted
(`git rm .github/dependabot.yml`).

SynACK is AGPL only. `LICENSE-COMMERCIAL` is deleted and the license fields in
`pyproject.toml`, `docker/Dockerfile` and `debian/copyright` name only
`AGPL-3.0-or-later`. If an upstream merge touches those lines or restores the
file, keep the AGPL-only version. Copyright and license headers inside source
files are upstream's and are left as they are.

## Seeing what SynACK changes

```sh
scripts-dev/synack-sync-upstream.sh --status
```

This prints the upstream base and a diffstat of every file that differs from
stock Synapse at that base. For the full diff:

```sh
base=$(sed -n 's/^commit: //p' .synack/UPSTREAM_BASE)
git diff $base HEAD
```

Current patches and the files they touch:

| Patch | Files |
| --- | --- |
| HTTP Range requests for local media | `synapse/media/_base.py`, `synapse/media/media_storage.py` |
| Legacy media endpoints fetch over federation | `synapse/rest/media/download_resource.py`, `synapse/rest/media/thumbnail_resource.py` |
| Remote media fallback through another homeserver | `synapse/config/repository.py`, `synapse/media/media_repository.py` |

Tests for all three are in `tests/media/test_base.py`,
`tests/media/test_media_storage.py` and `tests/rest/client/test_media.py`.

Keep this table and the list in `README.md` up to date whenever a patch is
added, changed or dropped.

## Merging a new upstream release

Start from a clean working tree, then:

```sh
scripts-dev/synack-sync-upstream.sh v1.162.0
```

The script:

1. Fetches the tag from upstream.
2. Compares **stock Synapse at the recorded base** with **stock Synapse at the
   new tag**. That is the true set of upstream changes since the last merge.
3. Compares the recorded base with `main` to get the SynACK changes, and lists
   the files changed by both sides.
4. Merges the new tag into the working tree using the recorded base as the
   merge base, updates `.synack/UPSTREAM_BASE`, and leaves the merge
   uncommitted for review.

The file lists are written to `.git/synack-sync/` (`upstream-changes`,
`synack-changes`, `overlap`).

### Rules for resolving the merge

- Keep the SynACK patches. An upstream change to the same file is merged with
  ours, not chosen over it.
- If upstream has implemented the same feature itself, prefer the upstream
  implementation and drop ours, unless ours still does something we need that
  theirs does not. Check for this even when the merge is clean: upstream may
  add the feature in different files, which produces no conflict. Search the
  upstream delta for it, for example:

  ```sh
  git diff <base> <new-tag> -- synapse/media synapse/rest/media | grep -n -i -E 'range|use_federation'
  ```

- For every file in `overlap`, look at both sides before accepting the result:

  ```sh
  git diff <base> <new-tag> -- <path>   # what upstream changed
  git diff <base> HEAD -- <path>        # what SynACK changed
  ```

  A clean automatic merge can still drop or break a SynACK line that sits next
  to an upstream change, so read the merged file, not only the conflict hunks.

### Before committing

- Search the tree for leftover conflict markers.
- Run the media tests:

  ```sh
  python -m twisted.trial tests.media tests.rest.client.test_media
  ```

- If a patch was dropped or changed, update `README.md` and the table above,
  and change the base version named in `README.md`.
- Commit the merge. The commit message is prepared as `Merge Synapse <tag>`.

To abandon a merge in progress: `git merge --abort`.

## Credentials

Never commit deployment files. `homeserver.yaml`, signing keys, log configs,
`.env` files, database dumps and similar are ignored by `.gitignore`; the
access token used by `remote_media_fetch_fallback` lives only in
`homeserver.yaml`.
