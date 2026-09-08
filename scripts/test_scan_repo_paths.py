"""Regression tests for scan_repo.py path handling.

The motivating bug (iter 20): when the calendar-tz emulator was given absolute
paths like `/Users/.../IdeaProjects/scheduler/<file>`, its regex
`(?i)(calendar|schedule|booking|...)` matched the `scheduler` substring in the
directory name itself — making every file in the repo pass the path filter,
regardless of whether the file was actually calendar code. Caller now passes
repo-relative paths via `f.relative_to(repo)`.

These tests carry the lessons from iter-17 through iter-20 and are the reason
each exclusion exists:

- relative-path matching (iter 20, the motivating bug above)
- Clock / storage-ts / getOrElse exclusions in CalendarNowWithoutExplicitTimezone
  (iter 19)
- adapter-receiver removal in StaffQueryMissingAppDefId (iter 20)

Run with: .venv/bin/python -m pytest scripts/test_scan_repo_paths.py -v
Or standalone: .venv/bin/python scripts/test_scan_repo_paths.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# Import from the project venv
sys.path.insert(0, str(Path(__file__).parent))
import scan_repo


def test_calendar_emulator_does_not_match_repo_name_in_absolute_path():
    """A file in /<anywhere>/scheduler/Foo.scala must NOT trigger the
    calendar emulator's path filter when given the repo-relative path."""
    rel_path = Path("Foo.scala")  # repo-relative, no "scheduler" anywhere
    text = """
package com.foo
class Foo {
  def bar(): DateTime = DateTime.now()
}
"""
    hits = scan_repo.scan_calendar_now_no_tz(rel_path, text)
    assert hits == [], (
        f"calendar emulator must not fire on non-calendar file "
        f"with repo-relative path; got {hits}"
    )


def test_calendar_emulator_fires_on_real_calendar_path():
    """A file under a calendar-named path WITH a bare DateTime.now() must fire."""
    rel_path = Path("backend/calendar-3/Foo.scala")
    text = """
package com.foo
class Foo {
  def bar(): DateTime = DateTime.now()
}
"""
    hits = scan_repo.scan_calendar_now_no_tz(rel_path, text)
    assert len(hits) == 1, (
        f"calendar emulator should fire on calendar-path file; got {hits}"
    )


def test_calendar_emulator_skips_clock_classes():
    """`class TestClock { var t = DateTime.now() }` must not fire."""
    rel_path = Path("backend/calendar-3/Clock.scala")
    text = """
package com.foo
class TestClock {
  var t = DateTime.now()
}
"""
    hits = scan_repo.scan_calendar_now_no_tz(rel_path, text)
    assert hits == [], f"Clock-class abstraction must be skipped; got {hits}"


def test_calendar_emulator_skips_getorelse_with_withzone():
    """`.getOrElse(DateTime.now()).withZone(tz)` must not fire — value is rezoned."""
    rel_path = Path("backend/calendar-3/Foo.scala")
    text = """
package com.foo
class Foo {
  def bar() = {
    val x = something.getOrElse(DateTime.now()).withZone(tz)
  }
}
"""
    hits = scan_repo.scan_calendar_now_no_tz(rel_path, text)
    assert hits == [], f"getOrElse-with-withZone must be skipped; got {hits}"


def test_calendar_emulator_fires_on_getorelse_without_withzone():
    """`.getOrElse(DateTime.now())` without .withZone must fire — fallback inherits local TZ."""
    rel_path = Path("backend/calendar-3/Foo.scala")
    text = """
package com.foo
class Foo {
  def bar() = {
    val x = something.getOrElse(DateTime.now())
    doStuff(x)
  }
}
"""
    hits = scan_repo.scan_calendar_now_no_tz(rel_path, text)
    assert len(hits) == 1, (
        f"getOrElse without withZone should fire (bare fallback); got {hits}"
    )


def test_staff_emulator_does_not_match_adapter_callers():
    """Calls to `staffMembersAdapter.X()` must not fire — the adapter is the
    scoping boundary (uses withAdapterIdentity internally)."""
    rel_path = Path("backend/foo/SomeService.scala")
    text = """
package com.foo
class SomeService(staffMembersAdapter: StaffMembersAdapter) {
  def bar() = staffMembersAdapter.queryAllStaffMembers()
}
"""
    hits = scan_repo.scan_staff_query_missing_appdefid(rel_path, text)
    assert hits == [], (
        f"staffMembersAdapter calls must not fire post-iter-20; got {hits}"
    )


def test_staff_emulator_fires_on_raw_service_caller():
    """Direct calls to `staffMembersService.queryAllStaffMembers()` without
    `appDefId` should fire — service has no scoping boundary."""
    rel_path = Path("backend/foo/SomeAdapter.scala")
    text = """
package com.foo
class SomeAdapter(staffMembersService: StaffMembersService) {
  def bar() = staffMembersService.queryAllStaffMembers()
}
"""
    hits = scan_repo.scan_staff_query_missing_appdefid(rel_path, text)
    assert len(hits) == 1, (
        f"staffMembersService raw call should fire; got {hits}"
    )


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_")]


def main():
    passed = 0
    failed = []
    for fn in TESTS:
        try:
            fn()
        except AssertionError as e:
            failed.append((fn.__name__, str(e)))
        else:
            passed += 1
            print(f"  ✓ {fn.__name__}")
    print(f"\n{passed}/{len(TESTS)} passed")
    if failed:
        print("\nFAILURES:")
        for name, msg in failed:
            print(f"  ✗ {name}\n    {msg}")
        sys.exit(1)


if __name__ == "__main__":
    main()
