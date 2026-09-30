# Recipe fixes, and a verification run against four codebases

Two defects were found in `YodaConditions` after the original experiment, both now fixed and
released (`1.2.0`, `1.3.0`). The unit suite grew from 8 to 10 cases to cover them.

## What was wrong

1. **Method-call operands were not actually excluded.** The spec requires the operand being moved
   to be a plain variable, field, or array element — never a method call. The implementation
   checked that the constant side was constant, but never checked what the *other* side was.
   `detail.length() > 0` was wrongly converted to `0 < detail.length()`. Fixed in `1.2.0` by adding
   `isSimpleReference`, which gates which operand may be moved.
2. **The exclusion didn't recurse through a chain.** `getChildren().length` is a `FieldAccess` at
   the top — the same shape as a plain `list.length` — but its target is a method call, and the
   check only looked at the outermost node. Found on one real site, in `gui`:
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

## Token savings from mgrep and rtk

Two additional tools were available during this run: `mgrep` (semantic code search) and `rtk` (a
CLI proxy that filters/condenses shell output before it reaches the model).

**`rtk` — substantial, and structural.** It runs on every shell command automatically, not
something an agent opts into. Its own local tracking for this work: 349 commands, 18.55M raw
output tokens condensed to 51K delivered (99.7%). Because that condensation happens before content
ever enters the conversation, it is already reflected in the billable-token figures above, not a
separate saving on top of them — verbose `mvn test` output (488 tests, Surefire noise) is exactly
the kind of content it exists to strip.

**`mgrep` — negligible for this task.** Available in all four runs, but barely used: two runs
didn't use it at all, and the two that did used it as a secondary check alongside exact
`git diff`/`grep`, which did the actual verification work in every case. This is a task-fit
mismatch rather than a tooling failure: verifying an operator flip is an exact-match question ("did
`<` become `>` at this byte position?"), and semantic search is the wrong tool for that by
construction.
