# Understanding — bundle hardening (#20)

## What the work really is

Four small, local features around a bundle that already builds and verifies, plus one honest
deferral:

| Gap (`CAPABILITY_ROADMAP.md:320-321`) | Verdict |
|---|---|
| `plumb bundle` CLI | Build: `verify`, `inspect`, `pack`. A third party should not need Python. |
| tar packaging | Build: deterministic `.tar` / `.tar.gz`, and `verify`/`inspect` accept an archive. |
| timestamps | Build: an optional signed `created` field. Self-asserted, not third-party — say so. |
| key rotation | Build: the mechanism already exists (OpenSSH `allowed_signers` is line-based). Test it, document it, no new code. |
| transparency log / sigstore | **Defer, with the reason written down.** It needs a third-party service and a crypto dependency; the bundle design is deliberately zero-dependency, and untested feature-detection is worse than a named gap. |

## Affected areas

`src/plumb/bundle/verify.py` (optional manifest field, archive handling stays in the CLI),
`src/plumb/bundle/build.py` (`created`), a new `src/plumb/bundle/pack.py`, a new
`src/plumb/cli/bundle.py`, `src/plumb/cli/__init__.py` (subcommand), `bundles/README.md`.

## Decisions

- **`verify_bundle` stays directory-based.** Archive support is a CLI convenience: extract to a
  temp dir, verify, drop it. Keeps the security-critical API small.
- **Extraction is a trust boundary.** A `.tar` is untrusted input: refuse absolute paths, `..`,
  links, devices, and any path outside the destination. Test that.
- **`created` is optional** and only present when the builder supplies it, so every existing
  bundle (and the byte-identical determinism tests) still hold.
- **`inspect` does not verify the signature** — it reads unauthenticated manifest fields and
  says so. Verification is `plumb bundle verify`, one command away.

## Pipeline placement

C6. No verdict path changes.
