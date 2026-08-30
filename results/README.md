# Results

**A third option was added later: the Moderne CLI with a global recipe marketplace and no build
changes - see [`option3-moderne-cli.md`](option3-moderne-cli.md). It is folded into the tables
below.**

Two fresh agents, no shared context, briefs byte-identical apart from one tooling paragraph,
separate 431 MB Maven repositories, run sequentially. Arm A was given OpenRewrite **and the
recipe in this repository, already written and tested**. Arm B was forbidden both.

Every figure below was re-derived by me after the fact: `mvn clean test` on JDK 25 in each arm's
own working copy, plus `audit/yoda-audit.py`.

## Cost

| Metric | Arm A (Moderne + provided recipe) | Arm B (by hand) | Option 3 (Moderne CLI) | B vs A |
|---|---:|---:|---:|---:|
| **Wall clock** | 33.3 min | **21.6 min** | see note | −35% |
| ├ tool execution | 5.6 min | 9.0 min | 4.6 min `mod build`, 4 repos | +61% |
| ├ model time | **21.3 min** | 8.3 min | n/a | **−61%** |
| └ idle | 6.5 min | 4.3 min | n/a | −34% |
| **Billable tokens** | 34.7 M | **6.7 M** | n/a | **−81%** |
| Output tokens | 114,811 | 56,566 | n/a | −51% |
| Turns | 259 | 97 | n/a | −63% |
| Tool calls | 157 | 51 | n/a | −68% |

**Why Option 3's cost column is mostly `n/a` rather than zero.** Arms A and B measure *an
agent performing a task* - designing the tool, applying it, verifying it. Option 3 as
evaluated is a sequence of tool invocations, so tokens, model time, turns and tool calls have
no comparable meaning and are marked `n/a` rather than misleadingly reported as 0. What *is*
comparable is machine time, in [`application-benchmark.md`](application-benchmark.md):
**10.0 s cold / 3.2 s warm**, against the build-plugin path's 23.3 s and the lexer's 0.21 s
on the same repo.

## Outcome

| | Baseline | Arm A | Arm B | Option 3 (Moderne CLI) |
|---|---:|---:|---:|---:|
| kiga3000 converted | 0 | **61** | 58 | **61** (public copy) |
| ccfmaster converted | 0 | **731** | **731** | **blocked** - licence |
| core converted | 2 | **1,363** | 1,350 | **blocked** - licence |
| gui converted | 137 | **1,856** | 1,734 | **blocked** - licence |
| **total converted** | - | **4,011** | 3,873 | **61 of a possible 4,089** |
| Sites still unconverted | - | 120 | 259 | not measurable for the private 3 |
| Files changed | - | 497 | 489 | 42 in kiga alone (vs 23 / 22) |

`mod build` succeeded on all four repos (274.8 s cold). `mod run` then refused all four with
`A valid license is required: this repository is not an open source repository`, because each
`origin` points at a private GitHub remote. The 61-site figure is from the public
`kiga-3000`, where the full cycle works with no licence and no tenant token.

**Tests, independently re-run on JDK 25 — both arms identical to baseline:**

| Repo | Baseline | Arm A | Arm B | Option 3 (Moderne CLI) |
|---|---|---|---|---|
| kiga3000 | 83 / 0 / 0 / 0 | **same** | **same** | **same** (via `mod exec`, confirmed directly) |
| core | 21 / 0 / 0 / 0 | **same** | **same** | not run |
| ccfmaster | 488 / 7 / 6 / 2 (473 pass) | **same** | **same** | not run |
| gui | compiles, no tests | **same** | **same** | not run |

Option 3 was held to the same bar: `mod exec -- mvn clean test` reports only
`✓ Execution succeeded` and does **not** surface counts, so they were read from
`.moderne/exec/<id>/exec.log` (`Tests run: 83, Failures: 0`) and confirmed with a direct
`mvn clean test`.

Both arms also confirmed the *individual* failing test methods in ccfmaster are unchanged, so the
equal counts are not a coincidence.

## This is the first run where the Moderne arm produced a better outcome

In the four migration experiments the outcomes were ties, or Arm B did slightly more. Here **Arm A
converted 138 more sites (+3.6%)** and left half as many unconverted. That is a real win, and it
came from two places:

- **Type attribution.** Arm A converted `Foo.someLimit` when the LST showed it was `static final`.
  Arm B, working from a lexer, could not distinguish a `static final` field from an instance field
  read, so it restricted itself to `UPPER_SNAKE_CASE` and declined those. Worth ~23 sites.
- **A judgement call on `gui/com.collabnet.ccf.migration`** (122 sites). Arm A converted it and
  flagged it as *not compile-verified* - that bundle is excluded from the Maven build because it
  imports `com.collabnet.ccf.api`, which exists in no artifact anywhere. Arm B skipped it precisely
  *because* it could not be compile-checked. Arm A bought coverage; Arm B bought assurance. Both
  defensible; they are the whole 122-site gap in `gui`.

## But it cost 5x the tokens, and the reason is instructive

+418% tokens is the **worst penalty of any run in this series** - and this was the run where Arm A
was handed a finished, tested recipe.

The decomposition says why. Arm A's **tool execution was lower** (5.6 min vs 9.0) but its **model
time was 2.6x higher** (21.3 min vs 8.3). It did not lose on machine work; it lost on thinking. It
built four things: an extended recipe (v1.1.0), an AspectJ runner that lifts conditions out of
`.aj` files into synthetic compilation units, a file-based runner for sources outside any Maven
root, and a verifier. Arm B built one thing - a Java/AspectJ lexer with a precedence-aware operand
extractor - and ran it.

**For a purely syntactic transformation, the LST's type attribution is mostly dead weight.** It is
what makes `rewrite:run` take 4:18-4:30 per large project (it parses and type-attributes the whole
codebase, and drags ccfmaster through a full AspectJ compile first), and it bought 23 sites out of
4,011. A lexer was the better-matched tool for this job. That is a narrower claim than "recipes
lose" - it is that this particular task does not need the thing OpenRewrite is expensive for.

## Neither arm inverted an operator

This was the failure mode to fear: `x < 0` becoming `0 < x` compiles fine and silently inverts the
condition. Both arms defended against it structurally, and both were right:

- Arm A: the flip table lives in the recipe, applied through `J.Binary.Type`, so no per-site
  decision exists to get wrong. It also wrote a `verify_yoda.py` that canonicalises every changed
  condition and requires before/after equivalence - and **negative-tested the checker** by
  hand-corrupting a condition to confirm it would be caught.
- Arm B: the direction is written once in a `FLIP` dict, so an inversion would have to be global,
  which its 65-case self-test and 83+21+473 passing tests would expose. It also read **all 395**
  relational conversions by hand before committing.

My own independent check found 0 mismatches on kiga3000 for both arms and ~17 apparent mismatches
elsewhere - **all of which turned out to be defects in my checker**, not in the arms. See
[`measurement-corrections.md`](measurement-corrections.md).

## What each arm got wrong

Arm A, self-reported: it first placed the recipe module *inside* `kiga3000`, whose unit-test
fixtures contain deliberately non-Yoda code - so the audit score for that repo got **worse** by
adding the tool that fixed it. It also spent time chasing an unconverted `meta == null` that turned
out to be inside a `/* */` comment, and its build-completion wait-loop grepped for `BUILD`, which
matches `Building CCFMaster`.

Arm B, self-reported: its first operand extractor treated `>` as a boundary unconditionally, so
`new ArrayList<URL>().size() == 0` produced `new ArrayList<URL>0 == ().size()`, and `List<URL>`
casts made `URL` look like an `UPPER_SNAKE_CASE` constant. Both were caught by its 65-case
self-test **before it touched a single repository file**, because it had written those cases in
anticipation.

And one of Arm A's headline findings did not survive verification at all - see
[`measurement-corrections.md`](measurement-corrections.md).
