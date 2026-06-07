# TryOptionUnwrappedAccess

Calling collection/accessor methods like `.size`, `.length`, `.head` on a Try or Option without unwrapping.

## Pattern

Try and Option types don't have `.size` directly — they're container types that must be unwrapped before accessing their contents.

```scala
// WRONG:
val result = trySomething()
println(result.size)  // Try[List[_]] has no .size

// RIGHT:
val result = trySomething()
println(result.map(_.size).getOrElse(0))  // unwrap then access
println(result.fold(_ => 0, _.size))      // fold to handle both cases
```

## Detection

Heuristic: identifiers with names containing "try", "result", "option", "opt", "maybe", followed by `.size|.length|.head|.tail|.last`, where no unwrap method (`.map`, `.fold`, `.getOrElse`, etc.) appears nearby.

## False Positives

- Variables named `myTryAgain` or `resultSet` (contain the substring but aren't Try/Option types)
- Legitimately-unwrapped code `result.map(_.size)` — detector checks for the unwrap

## References

Similar to SCHED-46920 logging bug (iter-29): `result.size` on a Try[List] should be `result.map(_.size).getOrElse(0)`.

Severity: medium (silent data loss in logs / reporting)
