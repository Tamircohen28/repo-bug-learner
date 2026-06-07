# rule-validator

Stage 5 of the repo-bug-learner pipeline. Compiles a synthesized Scalafix
rule and runs it against its example input/output pair using
[`scalafix-testkit`](https://scalacenter.github.io/scalafix/docs/developers/setup.html#testing).

## Layout

```
rule-validator/
  build.sbt
  project/
    build.properties      # sbt 1.10.x
    plugins.sbt           # sbt-scalafix
  rules/                  # rule sources (one Rule.scala per candidate)
    src/main/scala/fix/
    src/main/resources/META-INF/services/scalafix.v1.Rule
  input/                  # test inputs annotated with /* rule = ... */ + /* assert: ... */
    src/main/scala/fix/
  output/                 # expected outputs (identical to input for lint-only rules)
    src/main/scala/fix/
  tests/                  # the testkit runner
    src/test/scala/fix/RuleSuite.scala
```

## Adding a new candidate rule

Given a candidate at `out/candidates/cluster_NNN/` with `Rule.scala`,
`input.scala`, `output.scala`:

1. Copy `Rule.scala` to `rules/src/main/scala/fix/<RuleName>.scala`.
2. Register the rule's FQCN in
   `rules/src/main/resources/META-INF/services/scalafix.v1.Rule`
   (one FQCN per line, e.g. `fix.MissingWithAdapterIdentity`).
3. Copy `input.scala` to `input/src/main/scala/fix/<RuleName>.scala`,
   preserving the `/* rule = <RuleName> */` header at the top.
4. Copy `output.scala` to `output/src/main/scala/fix/<RuleName>.scala`.

## Running

```
sbt rules/compile     # compile just the rule (fast feedback for syntax errors)
sbt tests/test        # apply rule to input, diff against output, check /* assert: */ markers
```

A candidate is considered VALID when both commands succeed.
