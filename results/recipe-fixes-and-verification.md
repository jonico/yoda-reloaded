# Recipe fixes, and a verification run against four codebases

Two defects were found in `YodaConditions` after the original experiment, both now fixed and
released (`1.2.0`, `1.3.0`). The unit suite grew from 8 to 10 cases to cover them.

## Two exclusions the recipe now enforces

1. **Method-call operands are excluded.** The spec requires the operand being moved to be a plain
   variable, field, or array element — never a method call. `detail.length() > 0` must stay
   untouched (`0 < detail.length()` would be wrong). Fixed in `1.2.0` by adding
   `isSimpleReference`, which gates which operand may be moved.
2. **The exclusion recurses through a chain.** `getChildren().length` is a `FieldAccess` at the
   top — the same shape as a plain `list.length` — but its target is a method call, so the check
   needs to look past the outermost node, not just at it. Found on one real site, in `gui`:
   `dialogComposite.getChildren().length == 0`, an `==` comparison where reordering happens to be
   harmless (`==` is order-independent regardless of side effects) but still out of spec. Fixed in
   `1.3.0` by making `isSimpleReference` recurse into `FieldAccess`'s target and `ArrayAccess`'s
   indexed expression.

Both fixes ship with a regression test confirmed to fail on the pre-fix code and pass after.

**Scope of the second bug, verified precisely rather than by inspection:** ran both the pre-fix
(`1.2.0`) and post-fix (`1.3.0`) recipe against the same pre-transformation source for all four
codebases and diffed the two resulting patches directly. Byte-identical everywhere except the one
`gui` site above — the bug affected exactly one site across all four corpora.

## A tooling finding alongside them

The Moderne MCP server binds to whatever repository its host session started in, for the whole
session — not per subagent, not per working directory. A subagent that `cd`s into a different
repository and calls an `mcp__moderne__*` tool silently gets results for the *original* bound
repository, with no error. The `mod` CLI has no such binding — use it directly (it takes a path
argument) for any repository other than the one an existing MCP session is already bound to.

Two CLI-specific notes for anyone doing the same:

- `mod run <path> --recipe=<name>` does not write the working tree directly — it produces a patch
  only. `mod git apply <path> --last-recipe-run` applies it.
- Running a recipe with no `files`/path scoping crashes with a `ClassCastException` on a
  repository that has non-Maven-module Java source outside the build's reactor (a `legacy/`
  reference tree, a stray worktree directory). Scoping the run to the actual source roots avoids
  it.

## Verification run: fixed recipe, corrected tooling, four codebases

Same recipe (`1.3.0`), same task (Yoda-condition conversion inside `if` statements), one fresh
agent per repository, each independently re-verified afterward against the repository's actual
build/test commands — not against the agent's own report of them.

| Repo | Sites converted | Files changed | Billable tokens | Verification |
|---|---:|---:|---:|---|
| `kiga3000-reloaded` | 43 | 21 | 4.54M | 83/83 tests |
| `ccfmaster-reloaded` | 311 | 111 | 4.49M | 488/488 tests (7F/6E pre-existing, identical before/after) |
| `core-reloaded` | ~1,000–1,100 | 110 | 4.13M | 21/21 tests |
| `gui-reloaded` | ~1,180–1,290 | 153 | 5.73M | compiles clean, 254 files, no test suite |

Zero incorrect operator inversions across all four. No `.equals()` reordered. No non-`.java` file
touched.

## A genuine with/without comparison, now that the recipe is fixed

A fresh manual (no-Moderne) arm was also run on each of the same four repos, from the same
starting commit, each independently re-verified the same way.

| Repo | Recipe (fixed) | Manual | Ratio |
|---|---:|---:|---:|
| `kiga3000-reloaded` | 4.54M | 15.60M | 3.4x |
| `ccfmaster-reloaded` | 4.49M | 10.83M | 2.4x |
| `core-reloaded` | 4.13M | 16.41M | 4.0x |
| `gui-reloaded` | 5.73M | 70.26M | 12.3x |
| **Total** | **18.89M** | **113.10M** | **~6.0x** |

**This is the reverse of the original six-experiment finding**, which measured a recipe that had
the two defects above. The recipe's own application cost hasn't changed - a correct run was always
fast (~58 seconds of recipe work for a whole estate, measured in the original experiment). What
changed is that it now stays correct on the first try, so nothing downstream has to detect and
undo its mistakes. The manual side paid a larger version of the same tax the fixed recipe no
longer pays:

- **Every manual run built its own detector from scratch, and every one found a real bug in it
  before trusting it.** `ccfmaster`: a naive line-ending read/write silently converted the repo's
  CRLF files to LF, caught by a suspicious `git diff --stat`. `core`: two bugs caught by a
  dedicated self-test file built *before* touching the real repo - literal operands wrongly
  rejected, and the same CRLF issue. `gui`: the CRLF issue recurred independently in a completely
  different agent's from-scratch tooling; on top of that, a mid-chain method-call classifier gap
  (`dialogComposite.getChildren().length` - the exact shape fixed in the recipe above) had to be
  found and closed by hand, and disambiguating genuine `UPPER_SNAKE_CASE` constants from
  same-spelled enum members required grepping every `enum` declaration across all seven bundles.
- **The task wording was ambiguous about `==`/`!=` scope**, and one agent's defensible but
  unintended literal reading (Java Language Specification terms "relational operators" as
  `<,>,<=,>=` only) cost a full second pass over `gui` - its 70.26M reflects doing the work twice.
- **The CRLF bug appearing independently in two of four runs is the clearest single data point.**
  Neither agent saw the other's work; both wrote similar text-processing tools from scratch and
  both paid to discover and fix the identical mistake. A recipe operating on a parsed syntax tree
  doesn't have this problem structurally.
- **Comments are the one category the recipe is structurally immune to.** It can't "see" comment
  text - it isn't part of the parsed tree. A text/regex tool has to detect and skip comments
  correctly every run, and one manual run in this comparison got it wrong once (edited inside a
  `/* */` block comment containing example code, zero runtime effect) - the kind of mistake that
  is definitionally impossible for an AST-based recipe.

This isn't "recipes are always cheaper." A recipe that works correctly amortises its engineering
cost across every future run; hand-written tooling pays its engineering cost again, in full, every
time, because nothing about it is reused. The original experiment's finding - that a *broken*
recipe cost more than manual work - was true for the same underlying reason, stated the other way
around. Correctness, not the tool category, is what the cost tracks.

## Token savings from mgrep and rtk

Two additional tools were available during this run: `mgrep` (semantic code search) and `rtk` (a
CLI proxy that filters/condenses shell output before it reaches the model).

**`rtk` — substantial, and structural.** It runs on every shell command automatically, not
something an agent opts into. Its local tracking database records a `project_path` per command;
summed over exactly the paths this work touched (not a whole-machine total, which would mix in
unrelated concurrent activity): 625 commands, 19.09M raw output tokens condensed to 134,615
delivered (99.3%). Because that condensation happens before content
ever enters the conversation, it is already reflected in the billable-token figures above, not a
separate saving on top of them — verbose `mvn test` output (488 tests, Surefire noise) is exactly
the kind of content it exists to strip.

**`mgrep` — negligible for this task.** Available in all four runs, but barely used: two runs
didn't use it at all, and the two that did used it as a secondary check alongside exact
`git diff`/`grep`, which did the actual verification work in every case. This is a task-fit
mismatch rather than a tooling failure: verifying an operator flip is an exact-match question ("did
`<` become `>` at this byte position?"), and semantic search is the wrong tool for that by
construction.
