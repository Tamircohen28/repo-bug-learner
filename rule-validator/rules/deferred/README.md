# Deferred rules

Rules in this directory are **not loaded by the scanner**. They are
testkit-validated and shippable in principle, but fast-mode regex /
Semgrep emulation cannot reach ≥75% precision for them because they
require type-flow / data-flow analysis.

To enable these, run scalafix-cli or semgrep-pro with type info on the
target repo (requires SemanticDB or LSIF or type-aware semgrep license).

## Why each rule is here

### `calendar-now-without-explicit-timezone.yaml`
Real bug class (cross-repo evidence in scheduler + mobile + catalog-bo).
After 6 rounds of `pattern-not-inside` tightening, plateaued at ~30% TP
on bookings-mobile (38 findings, 3 TP). Remaining FPs require data-flow:
the rule cannot tell whether the `new Date()` reaches a tz-naive method
(`getHours/getDay/endOf`) or an instant-only sink (`.toISOString()`,
`.getTime()` arithmetic, fallback to tz-aware helper).
Sample findings to revisit when type info is available: see
`out/iterations/verify_iter16e_calendar_tz.md`.
