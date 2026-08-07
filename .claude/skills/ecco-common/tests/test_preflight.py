#!/usr/bin/env python3
"""
Offline tests for ecco_preflight (the environment guard). Fully synthetic — no venv
breakage needed: we probe a known-good lib and a known-missing name.

Run with the venv python:
    .venv/bin/python .claude/skills/ecco-common/tests/test_preflight.py
"""
import io
import os
import sys
import contextlib
import traceback

# ecco_preflight lives in the ecco-common/ dir (a sibling of the ecco_common/ package),
# so put that dir on the path — same as the skills' run.py do.
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(_HERE, "..")))

import ecco_preflight  # noqa: E402

TESTS = []


def test(fn):
    TESTS.append(fn)
    return fn


@test
def test_check_imports_ok_on_stdlib():
    ok, missing = ecco_preflight._check_imports(["os", "sys", "json"])
    assert ok and missing == [], (ok, missing)


@test
def test_check_imports_reports_missing():
    ok, missing = ecco_preflight._check_imports(["os", "totally_missing_pkg_xyz"])
    assert not ok, "should report failure"
    assert len(missing) == 1 and missing[0][0] == "totally_missing_pkg_xyz", missing


@test
def test_ensure_env_returns_true_when_healthy():
    # numpy is in the venv; ensure_env should pass silently and return True.
    assert ecco_preflight.ensure_env("test", libs=["numpy"], exit_on_fail=False) is True


@test
def test_ensure_env_returns_false_and_prints_on_missing():
    # With exit_on_fail=False it must NOT sys.exit — returns False and prints guidance.
    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        result = ecco_preflight.ensure_env("test-skill",
                                           libs=["totally_missing_pkg_xyz"],
                                           exit_on_fail=False)
    out = buf.getvalue()
    assert result is False, "should return False on unhealthy env"
    assert "ecco-setup" in out and "totally_missing_pkg_xyz" in out, out
    assert "test-skill" in out, "skill name should appear in the message"


@test
def test_ensure_env_exits_by_default():
    # Default exit_on_fail=True must raise SystemExit(1) on failure.
    buf = io.StringIO()
    try:
        with contextlib.redirect_stderr(buf):
            ecco_preflight.ensure_env(libs=["totally_missing_pkg_xyz"])
    except SystemExit as e:
        assert e.code == 1, f"expected exit code 1, got {e.code}"
        return
    raise AssertionError("ensure_env should have sys.exit(1) on failure")


def main():
    print("=" * 64)
    print("ecco_preflight tests")
    print("=" * 64)
    passed = failed = 0
    for fn in TESTS:
        try:
            fn()
            print(f"  [PASS] {fn.__name__}")
            passed += 1
        except Exception as e:  # noqa: BLE001
            print(f"  [FAIL] {fn.__name__}: {type(e).__name__}: {e}")
            traceback.print_exc()
            failed += 1
    print("=" * 64)
    print(f"{passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
