# ADR 002: Keep the required `CI` status check, against the standards policy

## Status

Accepted

## Context

`make repo-standards-gate` runs the shared branch-governance audit
(`scripts/github-policy.sh`) against the `Default Branch - PR & CI` ruleset. It
reports a CONFLICT it deliberately refuses to resolve:

```
✗ Default Branch - PR & CI — drifts from policy
⚠ Default Branch - PR & CI — CONFLICT: would remove required status check(s): CI;
  would remove protection rule(s) already in force: required_status_checks
```

The shared policy does not model a required status check for this repo, so
reconciling the ruleset to it would delete `required_status_checks` and the `CI`
context with it. That is strictly *less* protection than the repo has today.

The `CI` context is not incidental. It is the fan-in job in `ci.yml`
(`needs: [lint, test, agent-check, secret-scan]`) that exists specifically so a
single stable context can gate merges while the leaf jobs — including the
`3.11 / 3.12 / 3.13` test matrix — change freely underneath it. Removing it
would ungate the default branch entirely.

Historically the opposite failure has already cost this repo months: the ruleset
required a context named `CI` that no workflow reported, so every pull request
sat permanently blocked, which is why the Dependabot PR opened in July was still
open in September.

## Decision

Do not run `github-policy.sh apply` against this repository. The CONFLICT is
recorded here and treated as expected output, not as a gap to close. The audit
tool already refuses to make a repository less protected on its own, so the
conflict surfaces as a warning rather than a silent downgrade — the correct
behaviour, and the reason it is safe to leave standing.

Two settings must hold and are worth re-checking whenever this ruleset is
touched:

- `required_status_checks` keeps the single context `CI`.
- `strict_required_status_checks_policy` stays `false`. With it on, every merge
  marks every other open branch out of date and the one-PR-at-a-time flow stalls
  behind a serial rebase queue.

## Consequences

- `make repo-standards-gate` will keep reporting this CONFLICT. It is expected;
  do not "fix" it by applying the policy.
- If the shared policy later grows a way to declare a required context per
  repository, this ADR should be revisited and the divergence removed.
- Any new required check should be added as a dependency of the `CI` fan-in job
  rather than as a second required context, so the ruleset itself stays a
  one-line contract.
