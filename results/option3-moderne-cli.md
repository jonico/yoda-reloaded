# Option 3: Moderne CLI with a global recipe marketplace, no build changes

The first two options in this series are **Arm A** (OpenRewrite via build-plugin configuration -
`rewrite-maven-plugin` invoked per repo) and **Arm B** (hand-written tooling). This adds a third:
the **Moderne CLI** (`mod` 4.7.2) running recipes from a machine-global marketplace, with no edits
to any repo's build files.

Everything below was measured on this machine. Where a number is the CLI's own estimate rather
than a measurement, it is labelled as such.

## Headline: it works, and the licence gate decides whether you can use it

| | Private repositories | Public (open-source) repositories |
|---|---|---|
| `mod build` | **works** | **works** |
| `mod run` | **blocked** - `A valid license is required: this repository is not an open source repository` | **works, no licence, no tenant token** |

That is the single most important finding. The brief anticipated that a broken tenant token would
limit the path to open-source *recipes*; in fact it limits it to open-source *repositories*.
`mod run` refuses to execute **any** recipe - including one built locally from source - on a repo
whose `origin` points at a private remote.

`mod config license generate` exists but reads an Ed25519 **private key** that only Moderne holds,
so there is no local workaround. The two escapes are a working tenant connection or a
Moderne-issued licence key; neither is present here.

## The same recipe and repo set as the existing options

Recipe: `schnickschnackschnuck.rewrite.YodaConditions` - the same recipe Arm A used, installed into
the CLI marketplace. Repo set: the same four (`kiga3000`, `ccfmaster`, `core`, `gui`), plus the
public `jonico/kiga-3000` once the licence gate blocked the private four.

## Measurements

| Operation | Cold | Warm | Cache reuse reported |
|---|---:|---:|---|
| `mod build` - 4 private repos | **274.8 s** (4.6 min) | - | - |
| `mod build` - 1 public repo | **12.5 s** | **8.8 s** | - |
| `mod run` - 1 public repo | **10.0 s** | **3.2 s** | `10s` cold / `7s` warm "saved by using previously built LSTs" |
| `mod git apply` | 1 s | - | - |
| `mod exec -- mvn clean test` | 4 s | - | - |
| `mod study --recipe-run <id> --csv` | 1 s | - | - |
| recipe install into marketplace (by GAV) | 6.2 s | - | - |

**Discounted:** the CLI printed `3h 30m saved by using recipes`. The data table shows why that is
not a measurement: `estimatedTimeSaving` sums to **12,600 s across 42 files = exactly 300 s per
file**. It is a per-file constant, not an observation. The measured figure is 10.0 s cold.

## The "no build changes" claim: proven

After a full `build -> run -> git apply` cycle on the public repo:

```
build/config files touched: 0
```

Zero `pom.xml`, zero `build.gradle*`, zero `settings.gradle*`, zero `rewrite.yml`. Contrast with
the existing options on the CCF migration, where Arm A modified `pom.xml` **and** added
`rewrite.yml` in all three repos, and Arm B added neither.

`.moderne/` does not show up as untracked, because **the CLI writes its own exclusion into
`.git/info/exclude`**:

```
.moderne/*
!.moderne/moderne.yml
!.moderne/context/
```

So the brief's question - "add to `.gitignore`?" - answers itself for the local clone, but
`.git/info/exclude` is **not** shared. A teammate cloning the repo gets no exclusion, so for team
use it still belongs in a committed `.gitignore`.

## Correctness, verified the same way as the other options

Not accepted on "the patch applied cleanly", and not on the CLI's own word either. `mod exec`
reports a bare `✓ Execution succeeded` and does **not** surface test counts; those are only in
`.moderne/exec/<id>/exec.log`:

```
[INFO] Tests run: 83, Failures: 0, Errors: 0, Skipped: 0
[INFO] BUILD SUCCESS
```

Confirmed independently with a direct `mvn clean test` (3.1 s, same 83/0/0/0).

## Scope: the CLI converted *more* than either existing option, including things it should not have

61 of 61 eligible sites in `src/` - identical to Arm A. But the file count differs sharply:

| | Files changed in kiga | Which areas |
|---|---:|---|
| Arm A (build plugin) | 23 | `src/` only |
| Arm B (hand lexer) | 22 | `src/` only |
| **Option 3 (CLI)** | **42** | `src/` 22, **`legacy/` 12**, **`experiment/*.py` 5**, `tools/` 3 |

Two of those are findings, not features:

**It rewrote the vendored 2006 originals.** `legacy/rb_1_3/` is the untouched recovered CVS
snapshot, kept precisely so later changes stay auditable against it. Both existing options skipped
it because it is on no source path. The CLI's recursive scan does not care about source paths.

**It rewrote Python.** Five files under `experiment/` changed:

```diff
-if __name__ == "__main__":
+if "__main__" == __name__:
```

A **Java** recipe - a `JavaIsoVisitor` over `J.Binary` inside `J.If` - fired on Python sources,
because the CLI's polyglot LST maps Python onto the same `J` tree types. The output is valid
Python and behaviour-preserving (verified: `ast.parse` succeeds, and the script's runtime error is
an identical pre-existing `IndexError` from missing `argv` before and after). But no recipe author
asked for it, and neither existing option could have done it - the plugin path parses only Java,
and Arm B's lexer globbed only `.java`/`.aj`.

This is genuinely double-edged: cross-language reach is a real capability, and uninstructed
cross-language reach is a real hazard.

## Setup obstacles the other options do not have

1. **`mod config recipes jar install` takes a GAV, not a file path.** Installing a locally built
   jar by path fails: `The GAV parameter must be a two or three part coordinate`. A local Java
   recipe must first be published into a Maven-layout repository, which is then added with
   `mod config recipes artifacts maven add file://...`. YAML recipes *can* be installed from a
   `file://` path directly.
2. **`mod` discovers repos through the git `origin` remote.** With remotes stripped, `mod list`
   reported `Found 1 organization containing 0 repositories`. Re-adding them gave 4. A repo with no
   remote is invisible.
3. **`mod build` uses the default `~/.m2` and cannot be redirected.** No `--maven-repo-local`, no
   argument passthrough. The first cold build managed 1 of 4 repos; the three failures were all
   `Could not find artifact ccf.vendored:...` / `com.collabnet.ccf:ccf-core`. **The isolated
   per-arm Maven repository this experiment series uses as a control is unusable with the CLI.**
   Proceeding required installing 18 vendored artifacts, a reconstructed Roo stub and `ccf-core`
   into the *default* `~/.m2` - trading an experimental control for global mutable state.

## Costs the other options do not have

| Cost | Measured |
|---|---|
| Global recipe store | **115 MB** `~/.moderne/cli/recipes` |
| Global Maven cache | **142 MB** `~/.moderne/cli/maven-cache` |
| Per-repo LST + run artifacts | **19 MB** across 4 repos (3.6 / 6.3 / 4.8 / 4.4) |
| Global mutable state | one marketplace, one artifact-source list, one licence, shared by every project on the machine. `mod config recipes artifacts show` prints "Set globally for all repositories" |
| Default `~/.m2` pollution | forced, per finding 3 above |
| Version coupling | the CLI version is a machine-wide install, not pinned per repo the way a build plugin is |

**Security note:** the tenant-token failure prints the rejected bearer token in cleartext inside a
suggested `curl` reproduction. That token should be rotated.

## Capabilities the other options do not have

- **One recipe run fanning out over N repos** from a parent directory, discovered by recursive
  scan - `Found 1 organization containing 4 repositories`.
- **Cross-repo data tables.** `mod study --recipe-run <id> --data-table
  org.openrewrite.table.SourcesFileResults --csv` produced an *org-level aggregate* whose columns
  are `repositoryOrigin, repositoryPath, repositoryBranch, sourcePath, afterSourcePath,
  parentRecipe, recipe, estimatedTimeSaving, cycle`. Neither existing option produces anything
  comparable; Arm B's equivalent was a hand-written TSV.
- **`mod git checkout/apply/commit/push` batch branch-and-PR flow**, and `mod exec` running a
  verification command from each repo's detected build-tool directory with `MODERNE_BUILD_TOOL*`
  exposed.
- **No per-repo onboarding.** Zero build-file edits, versus Arm A's `pom.xml` + `rewrite.yml` in
  every repo.
- **A 1,433-recipe catalogue already resolved**, and deep composites: `mod config recipes tree
  org.openrewrite.java.spring.boot3.UpgradeSpringBoot_3_0` resolves to 648 distinct recipes at
  depth 12 (~55 s).

## Dimensions that genuinely do not apply

- **Token cost / model time / turns / tool calls.** The existing comparison measures *an agent
  doing a migration*. Option 3 as evaluated here is a tool invocation, not an agent run, so these
  are not comparable and are marked `n/a` rather than zero. The nearest honest analogue is the
  application benchmark below.
- **"Sites converted" for the private four repos.** `mod run` never executed, so there is no
  figure. Not zero - unmeasurable under the current licence state.
