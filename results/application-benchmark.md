# Application benchmark: what it costs to *run* each implementation

The A/B results measure the whole job — designing the tool, applying it, verifying it. A fair
follow-up question is what happens if you **discard all the design work** and count only the
marginal cost of applying a tool that already exists. That is the strongest framing available for
the recipe approach, because a recipe is a one-time cost that amortises.

So I measured it.

## Setup

Both implementations applied to a **fresh checkout of `core` at its pre-Yoda baseline**
(`0f3479a1`) — 2,833 `if` statements, ~1,400 eligible sites, 8 source roots in one Maven module.
Same machine, nothing else running.

For the OpenRewrite side I deliberately used **`org.openrewrite.staticanalysis.RemoveExtraSemicolons`**,
a recipe that does almost nothing on this codebase, rather than the Yoda recipe. That isolates the
cost of the *pipeline* — forked lifecycle, LST parse, whole-project type attribution — from the
cost of any particular recipe's logic.

## Result

### On `core` (~1,400 sites) — the original two options

| | Wall clock | Tokens | Sites converted |
|---|---:|---:|---:|
| `lexer/yoda.py` (Arm B) | **1.16 s** | ~0 | 1,356 in 101 files |
| `rewrite:dryRun` pipeline (Arm A) | **266.4 s** | ~0 | — (trivial recipe) |
| **Moderne CLI (Option 3)** | **blocked** | n/a | **unmeasurable** — `mod run` refuses private repos without a licence |

### On the public `kiga-3000` — all three, same corpus

`core` is a private repo, so Option 3 cannot run there at all. Re-measured on the one repo all
three can process, so the third column is real rather than inferred:

| | Wall clock | Sites converted | Files touched |
|---|---:|---:|---:|
| `lexer/yoda.py` (Arm B) | **0.21 s** | 49 (58 Yoda after) | 19, `src/` only |
| `rewrite:dryRun` pipeline (Arm A) | **23.3 s** | — (trivial recipe) | — |
| **`mod run` (Option 3)** | **10.0 s cold / 3.2 s warm** | **61 (61 Yoda after)** | **42** — `src/` 22, `legacy/` 12, `*.py` 5, `tools/` 3 |

Three things fall out of that row:

- **The CLI is ~2.3x faster than the build-plugin path on the same repo** (10.0 s vs 23.3 s cold,
  3.2 s warm), because it caches LSTs in `.moderne/build` and reports the reuse explicitly:
  `7s saved by using previously built LSTs`. The plugin re-parses from scratch every invocation.
- **It is still ~48x slower than the lexer** (10.0 s vs 0.21 s), for the same reason as Arm A: a
  purely syntactic edit pays for whole-project type attribution it never uses.
- **It converted more, including things it should not have.** 61 sites against the lexer's 58 - the
  3-site gap is `String.class` class literals, which the lexer declines - but also 20 files outside
  `src/`: the vendored 2006 `legacy/` originals, and five Python files where a **Java** recipe
  rewrote `if __name__ == "__main__":` into `if "__main__" == __name__:`.

One incidental finding from this run: the lexer needed `--encoding latin-1` to read kiga at all
(`CheckKarteiKarte.java` has an ISO-8859-1 `ü` at byte 447). Both LST-based options handled the
encoding without being told.

**230x.** And the 266.4 s I measured matches Arm A's self-reported 4m26s for `core` **exactly**,
which is a useful cross-check on both numbers: the cost is intrinsic to the pipeline, not to its
Yoda recipe.

Arm A's own per-project times show the same shape — 7 s on `kiga3000` (9k LOC) against 4:18, 4:26
and 4:30 on the three large repositories. The pipeline cost scales with the size of the codebase it
has to type-attribute, not with the number of sites it changes.

## What this does and does not show

**It collapses the token gap.** Applying either tool is a single command. The entire 5x token gap
in the main results (34.7 M vs 6.7 M) was **design and thinking work**: extending the recipe,
writing the AspectJ splicer, the file runner and the verifier. Discard that and neither approach
costs meaningful tokens to apply. If the recipe already exists, running it is free.

**It inverts the wall-clock comparison.** For a purely *syntactic* transformation you pay the full
price of type attribution and use none of it. In this experiment the type information bought Arm A
**23 sites out of 4,011** — the mixed-case `static final` constants a lexer cannot distinguish from
an instance field read.

**It does not settle reusability, which is the real argument for the recipe.** Arm A's artifact is
committed, versioned, unit-tested and published; it was written during the `rock_paper_scissors`
run against **2 sites** and then genuinely carried into this run against 4,091. That is
amortisation working as advertised.

But it is not exclusive to recipes. Arm B's implementation is 450 lines with a 65-case self-test,
and it was **deliberately left in `/tmp` and never committed** — it survived to be benchmarked here
only by luck. That was a choice, not a limitation. Committed, it would amortise identically *and*
run 230x faster. So the honest claim is that a recipe beats *ad-hoc* scripting on reuse, not that
it beats *disciplined* scripting.

Both implementations now live in this repository — [`recipe/`](../recipe) and
[`lexer/`](../lexer) — so the comparison stays reproducible.

## Where this framing would favour the recipe

Anything needing **type resolution across a classpath**: the `javax` to `jakarta` migration,
`Mockito1to5Migration`, `JUnit4to5Migration`, dependency upgrades. There the LST cost buys the
thing that makes the transformation possible at all, and a lexer cannot do the job at any speed.

The transformation in this repository is the opposite case — moving a constant to the left of an
operator needs no types — which is why it is a clean measurement of what the pipeline costs when
you are not using what it provides.
