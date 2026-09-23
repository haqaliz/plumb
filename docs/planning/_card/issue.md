# C2 Artifact intake & pinned environment — issue card

Source: inline brief from the repo's own capability roadmap and design docs (no GitHub issue —
the id is a slug). Capability text: `docs/technical/CAPABILITY_ROADMAP.md` C2 (lines 51-60);
design: `docs/technical/ARCHITECTURE.md` C2 (lines 75-82); phase: `docs/ROADMAP.md` Phase 0
"C2 (minimum): resolve a local path or git URL to a pinned checkout on the user's compute."

## Brief

**C2 — Artifact intake & pinned environment.** Resolve the code/data behind the paper — a
local path, an `https` git URL with `--rev`, or an archive — into a **pinned checkout** (tree
hash recorded) and build a reproducible environment on the **user's compute**. Why:
reproducibility is impossible without a pinned, rebuildable environment. Depends on nothing
(the first unshipped capability; C1 is complete on the `c1-pdf-input` branch). Guardrail:
constraint #2 — everything stays local; nothing is fetched to a third party the user didn't
authorize. Environment build policy (ARCHITECTURE.md:79-80): lockfile-first, then declared
deps, then a best-effort resolve that is recorded as such. Isolation posture is documented and
recorded in the bundle (ARCHITECTURE.md:82; open question at :164-166). Tests stay offline
and deterministic: git resolution is exercised over local `file://` repos, archives are
synthetic, env-descriptor logic is tested with fake manifests, and the real `uv sync` runs
only in a dev-time demo — never in CI. The Phase 0 gate's C2 minimum is the acceptance bar:
a local path or git URL resolves to a pinned checkout on the user's compute.