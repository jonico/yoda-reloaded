# A measurement of mine that was wrong twice

I published, in this repository's README and in the experiment brief handed to the Moderne arm,
that the provided recipe "skips comparisons nested inside a method call — **126 of 3,864 sites
(3.3%)**".

**That figure is wrong. The real number is 2.**

## What I did wrong

My test for "is this comparison nested inside a method call" was:

```python
before = condition[:match.start()]
if re.search(r'[A-Za-z_][A-Za-z0-9_.]*\($', before.rstrip()) or before.count('(') > before.count(')'):
    nested_in_call += 1
```

The second clause treats **any** unclosed `(` as a method call. Most unclosed parens in a Java
condition are **grouping** parens:

```java
if (state == CoreState.STOPPED && (command == START || command == RESTART))
if ((character == 0x9) || (character == 0xA) || (character == 0xD))
if ((obj == null) || (obj.getClass() != this.getClass()))
```

Every comparison inside those brackets was counted as unreachable. They were never unreachable:
the recipe recurses through `J.Parentheses` explicitly, which I had even quoted approvingly when
describing how it works. Splitting the 126 by whether the innermost unclosed paren is preceded by
an identifier gives **114 grouping / 12 call**.

Then the corrected count of 12 was **also** inflated, by a second flaw. My literal-and-identifier
regex used

```python
IDENT = r'[A-Za-z_][A-Za-z0-9_.\[\]()]*'
```

which includes `)`. So in `getFromTable(a, b, c) != null` the match starts at `c)` rather than at
the whole call, leaving `getFromTable(a, b, ` as the "before" text — one unclosed paren, flagged as
nested. The call is an *operand* of the comparison, which the recipe handles perfectly well.

## The trustworthy number

The Moderne arm re-derived it with a token-accurate audit that masks comments and string bodies,
then tokenises and locates real comparisons at every nesting level. Its answer: **2 sites**, both
in `core`'s `ProjectTrackerReader`, and both actually excluded for a different reason (they sit in
the condition of a ternary, which the spec puts out of scope).

Its verdict on my figure, which I am recording verbatim because it is correct:

> The headline limitation — comparisons nested inside a method call, "126 of 3,864 sites (3.3%)" —
> is not borne out in this corpus. The true figure is 2 sites. 1,297 conditions contain both a call
> and a comparison, but in almost all of them the call is an *operand* (`x.size() > 0`), which
> 1.0.0 handled fine. I suspect the 3.3% was measured by pattern-matching "condition contains a
> call and a comparison".

That is close to exactly what happened.

## What it cost

This was not a harmless mistake in a footnote. I put the figure in the brief as a "known
limitation, measured rather than assumed", and the arm spent roughly twenty minutes extending the
visitor to cover method-call arguments, casts, array indexes and non-short-circuit operators — work
it reported as buying **2 sites**. It also reported the extension as worth doing "to remove the
doubt", which is a generous reading of being sent after a number I had got wrong.

## The lesson, for this project specifically

I have now been burned three times in this project by regex-based measurement of Java source:

1. Reading `.lastUpdated` file mtimes as live agent activity, when they were artefacts of my own
   `tar` copy.
2. Counting grouping parens as method calls, here.
3. An `IDENT` pattern containing `)`, which makes matches start mid-expression, also here.

The pattern is the same each time: a cheap textual proxy for a structural question, presented with
more precision than it earns. The audit script in this repository still uses regex and still has
a floor it cannot go below — that is documented in `audit/` — but any figure derived from it that
gets put in front of another agent or into a public issue should be re-derived with a parser first.
