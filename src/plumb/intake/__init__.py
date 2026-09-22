"""C2 artifact intake: resolve and pin the code/data behind a paper.

The public seam of the intake package. Four slices land here: deterministic
tree hashing (`tree.py`), source resolution to pinned checkouts (`checkout.py`),
manifest scan + environment descriptor (`manifest.py`, `env.py`), and this
seam plus the dev-time demo (`tools/demo_env_build.py`).

**Nothing here emits a verdict.** Intake produces pinned records — a checkout's
content address, its source provenance, and a reproducible environment
descriptor — which the run (C3) and verdict (C4) layers consume. It never
decides `REPRODUCED`/`DIVERGED`/`UNVERIFIED`; execution does.

**Named failure causes** — every intake failure resolves to one of these,
never a silent drop. When C4 lands, each maps to a future `UNVERIFIED` verdict
with that cause recorded:

| Cause | Raised when | Future `UNVERIFIED` cause |
|---|---|---|
| `SourceNotFound` | path doesn't exist / isn't a directory or archive; git clone fails; not a git repo | `SOURCE_NOT_FOUND` |
| `RevNotFound` | the requested git revision doesn't resolve in the source | `REV_NOT_FOUND` |
| `UnsupportedArchive` | unknown archive format, unreadable archive, or a member escaping the destination | `UNSUPPORTED_ARCHIVE` |
| `EnvBuildFailed` | no runner supplied (offline guard) or the recorded policy's runner fails | `ENV_BUILD_FAILED` |

**Offline contract.** Tests never touch the network (the autouse blocker in
`tests/conftest.py` covers them) and never run the real build: git resolution
runs against local `file://` repos, archives are synthesized in-process, and
the env runner is a stub. The one real `uv sync` in the repo is
`tools/demo_env_build.py`, run at dev time only. Tool versions (`git`, `uv`)
are recorded in the descriptor via `--version` probes.
"""

from __future__ import annotations

from plumb.intake.causes import (
    EnvBuildFailed,
    RevNotFound,
    SourceNotFound,
    UnsupportedArchive,
)
from plumb.intake.checkout import (
    Checkout,
    SourceRecord,
    resolve_archive,
    resolve_git,
    resolve_local,
)
from plumb.intake.env import (
    EnvBuild,
    EnvDescriptor,
    build_environment,
    describe_environment,
    uv_sync_runner,
)
from plumb.intake.manifest import ManifestScan, scan_manifests
from plumb.intake.tree import TreeHash, git_tree_hash, plumb_tree_hash

__all__ = [
    "Checkout",
    "EnvBuild",
    "EnvBuildFailed",
    "EnvDescriptor",
    "ManifestScan",
    "RevNotFound",
    "SourceNotFound",
    "SourceRecord",
    "TreeHash",
    "UnsupportedArchive",
    "build_environment",
    "describe_environment",
    "git_tree_hash",
    "plumb_tree_hash",
    "resolve_archive",
    "resolve_git",
    "resolve_local",
    "scan_manifests",
    "uv_sync_runner",
]