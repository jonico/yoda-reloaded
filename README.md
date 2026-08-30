# yoda-reloaded

A working OpenRewrite recipe that converts comparisons inside `if` conditions to **Yoda style**
(constant on the left), and the A/B experiment that applies it to **~4,089 sites across four
codebases**.

There is no Yoda recipe in OpenRewrite. I checked all six recipe modules —
rewrite-static-analysis 2.41.0, rewrite-migrate-java 3.42.1, rewrite-testing-frameworks 3.44.0,
rewrite-spring 6.37.1, rewrite-hibernate 2.25.0, rewrite-java-dependencies 1.60.2 — and none
contains one in either direction. The conventional static-analysis direction is the opposite of
this: removing Yoda conditions, not adding them.

## Why this exists

It came out of a series of controlled experiments comparing migrating legacy Java **with** and
**without** Moderne/OpenRewrite ([summary](https://github.com/jonico/ccf-modernized-summary)).
The recipe was written by the Moderne arm of the smallest of those experiments, on a project with
exactly **two** eligible sites — where hand-editing two lines would plainly have been faster. Its
author's reasoning, verbatim:

> Two operators on two lines would have been faster by hand, but the recipe is what makes the
> *spec* checkable instead of my reading of it.

So the interesting question is not whether it works. It is whether a recipe written once, at
two sites, **amortises** when pointed at four thousand. That is what the experiment in this
repository measures.

## The spec

Deliberately narrow, so it is unambiguous and behaviour-preserving:

- Applies to `==`, `!=`, `<`, `<=`, `>`, `>=` **inside an `if` condition only**. Comparisons in
  `while`, `for`, ternaries, `return` statements and assignments are left alone.
- Applies only where **exactly one** operand is a literal or a constant: a number, char, string,
  `true`/`false`/`null`, or an `UPPER_SNAKE_CASE` reference (bare or dotted). If both sides are
  constant, or neither is, nothing happens.
- **Relational operators are flipped on swap**: `x < 0` becomes `0 > x`; `x >= n` becomes
  `n <= x`. `==` and `!=` are symmetric and keep their operator. **Getting this wrong inverts the
  condition while still compiling**, which is the whole hazard of the task.
- `x.equals("lit")` is **not** turned into `"lit".equals(x)`. That changes null behaviour. Method
  invocations are not `J.Binary` nodes, so this is excluded structurally rather than by a special
  case.

## Two implementations of the same spec

| | What it is | On `core` (~1,400 sites) | On public `kiga-3000` |
|---|---|---:|---:|
| [`recipe/`](recipe) via **build plugin** | OpenRewrite `JavaIsoVisitor`, 8 unit tests — Arm A's, `rewrite-maven-plugin` wired per repo | 266 s | 23.3 s |
| [`lexer/`](lexer) | Hand-written Java/AspectJ lexer + precedence-aware operand extractor, 65 self-test cases — Arm B's | **1.2 s** | **0.21 s** |
| [`recipe/`](recipe) via **Moderne CLI** | Same recipe, installed into a machine-global marketplace, **zero build-file edits** — Option 3 | **blocked** (private repo, no licence) | 10.0 s cold / **3.2 s** warm |

Option 3 is written up in [`results/option3-moderne-cli.md`](results/option3-moderne-cli.md). Its
short version: the CLI runs the *same* recipe with no build changes at all and caches LSTs between
runs, which makes it ~2.3x faster than the plugin path on a repo both can process — but `mod run`
refuses private repositories without a Moderne licence or tenant token, and it converted 20 files
that neither other option touched, including five Python files.

Both are preserved here, so the comparison stays reproducible. Arm B's was deliberately *not*
committed by its author and survived only by luck; keeping it makes the reuse argument honest in
both directions. See [`results/application-benchmark.md`](results/application-benchmark.md) —
**230x**, measured with a trivial recipe so it isolates pipeline cost from recipe logic.

## The recipe

[`recipe/src/main/java/.../YodaConditions.java`](recipe/src/main/java/schnickschnackschnuck/rewrite/YodaConditions.java)
— a `JavaIsoVisitor` whose `visitIf` rebuilds **only** the condition, so the bodies can never be
touched. It recurses through `J.Parentheses`, `J.Unary`, `&&` and `||`, so each eligible
comparison in a compound condition converts independently.

The detail worth stealing: it moves whitespace with the **padding slots** rather than with the
expressions, so `if (choice < 0)` becomes `if (0 > choice)` and not `if (0 >choice )`.

8 unit tests pin the spec, including the four must-not-change classes: `equals` calls,
comparisons outside `if` conditions, already-Yoda comparisons, and comparisons where both or
neither side is constant.

### Known limitations, measured rather than assumed

- **Skips comparisons nested inside a method call.** `if (foo(x < 0))` is not converted, because
  `yodaify` returns unchanged for `J.MethodInvocation`. **The real figure is 2 sites across the
  four corpora**, not the "126 of 3,864 (3.3%)" I originally published here. That number was
  wrong, twice over, and the correction is recorded in
  [`results/measurement-corrections.md`](results/measurement-corrections.md) because I had already
  put it in the experiment brief.
- `isConstant` recognises `UPPER_SNAKE_CASE` only. Mixed-case constants and enum constants in
  other conventions are not treated as constants.
- **AspectJ `.aj` files are unreachable.** OpenRewrite has no AspectJ parser, so the 125 ITDs in
  `ccfmaster` are outside the reach of this or any recipe.

## The corpora

| Corpus | `if` statements | Already Yoda | Sites to convert | Tests protecting it |
|---|---:|---:|---:|---:|
| [`kiga3000`](https://github.com/jonico/kiga3000-reloaded) | 119 | 0 | 61 | **83** |
| [`ccfmaster`](https://github.com/jonico/ccfmaster-reloaded) | 1,093 | 0 | 737 | 473 |
| [`core`](https://github.com/jonico/core-reloaded) | 2,833 | 2 | 1,416 | 21 |
| [`gui`](https://github.com/jonico/gui-reloaded) | 3,123 | 137 | 1,875 | **none** |
| [`rock_paper_scissors`](https://github.com/jonico/rock_paper_scissors-reloaded) | 17 | 0 | 2 | 54 |
| **total** | **7,185** | **139** | **4,091** | |

`kiga3000` is the smallest but has the densest test coverage per line, so it is the corpus most
likely to catch an inverted operator. `gui` holds 46% of all sites and has **zero** tests — a
wrong flip there would be caught by nothing but review.

`gui`'s 137 already-Yoda sites are mostly the `CONSTANT.equals(x)` idiom, which this recipe
correctly refuses to create but also correctly leaves alone.

## Auditing

[`audit/yoda-audit.py`](audit/yoda-audit.py) reports `if_statements`, `already_yoda` and
`to_convert` for any directory, and is the objective measure both experiment arms are scored
against. [`audit/baseline.txt`](audit/baseline.txt) is the pre-experiment snapshot.

```bash
python3 audit/yoda-audit.py "label=/path/to/src"
```

## Results

Full detail in [`results/`](results/README.md). Headline:

| | Arm A (Moderne + this recipe) | Arm B (by hand) |
|---|---:|---:|
| Wall clock | 33.3 min | **21.6 min** |
| Billable tokens | 34.7 M | **6.7 M** |
| Sites converted | **4,011** | 3,873 |
| Tests | identical to baseline | identical to baseline |

**Arm A converted 138 more sites and cost 5x the tokens.** This is the first run in the series
where the Moderne arm produced a materially better outcome - and it was also handed a finished
recipe, so the +418% token penalty is the worst of any run.

The reason is in the decomposition: Arm A's *tool* time was lower, its *model* time 2.6x higher. It
built an extended recipe, an AspectJ condition-splicer, a file runner and a verifier; Arm B built
one lexer. For a purely syntactic transformation the LST's type attribution is mostly dead weight -
it is what makes `rewrite:run` cost 4:18-4:30 per large project, and it bought 23 of 4,011 sites.

**Neither arm inverted an operator.** My own independent checker reported ~17 mismatches, every one
of which was a bug in my checker - documented in
[`results/measurement-corrections.md`](results/measurement-corrections.md).
