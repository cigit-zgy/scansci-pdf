# paper_download operating profiles

These profiles narrow ScanSci for the `cigit-zgy/paper_download` authorization
boundary. They do not remove upstream features. Profile guards are applied after
user configuration so saved defaults cannot silently re-enable excluded routes.

Activate one profile with either:

```bash
export SCANSCI_PDF_PROFILE=institution_bulk
```

or:

```bash
scansci-pdf config-cmd project_profile institution_bulk
```

`institution_bulk` uses legal/OA/publisher API routes for the automatic pass and
returns unresolved browser/login work as `status=deferred`. The caller derives
the human phase from those result rows after all automatic work completes.

`home_personal` is serial and permits the normal visible institutional login and
manual human-verification flow for a small number of papers. It does not treat a
personal Elsevier API key as subscription entitlement.

Both profiles force `legal_only`, disable Sci-Hub/LibGen/SciBban lanes, Tor,
proxy pools, static browser proxies, FlareSolverr, automatic Turnstile handling,
and supplementary downloads. Explicit per-call grey or Tor requests return
`profile_policy_blocked` before network work.

Elsevier credentials remain outside Git. Use the existing local config or the
`ELSEVIER_API_KEY` environment variable. Never put a key on a command line that
will be logged. The key authenticates an API application; subscribed full text
still requires actual entitlement, such as a recognized institutional network.

## Upstream update procedure

```bash
git fetch upstream
git log --oneline HEAD..upstream/main
git diff HEAD...upstream/main -- src tests pyproject.toml uv.lock
```

Review changes to defaults, source selection, browser/challenge handling, and
credential logging before merging. Then run the focused profile-policy tests,
the relevant upstream acquisition tests, and the `paper_download` adapter tests.
Merge an accepted upstream change normally; never update the fork by force or by
silently replacing the reviewed baseline.
