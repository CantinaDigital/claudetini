#!/usr/bin/env python
"""Run E2E tests with fixture generation.

Usage:
    python tests/run_e2e.py           # Generate fixtures and run all tests
    python tests/run_e2e.py --quick   # Run tests without regenerating fixtures
    python tests/run_e2e.py --gen     # Only generate fixtures
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
FIXTURES_SCRIPT = ROOT / "tests" / "fixtures" / "generate_fixtures.py"
E2E_TESTS = ROOT / "tests" / "e2e" / "test_project_scenarios.py"


def generate_fixtures() -> bool:
    """Generate test fixtures."""
    print("\n" + "=" * 60)
    print("GENERATING TEST FIXTURES")
    print("=" * 60 + "\n")

    result = subprocess.run(
        [sys.executable, str(FIXTURES_SCRIPT)],
        cwd=ROOT,
    )
    return result.returncode == 0


def run_tests(verbose: bool = True) -> bool:
    """Run E2E tests."""
    print("\n" + "=" * 60)
    print("RUNNING E2E TESTS")
    print("=" * 60 + "\n")

    args = [sys.executable, "-m", "pytest", str(E2E_TESTS)]
    if verbose:
        args.append("-v")
    args.append("--tb=short")

    result = subprocess.run(args, cwd=ROOT)
    return result.returncode == 0


def main():
    args = sys.argv[1:]

    if "--gen" in args:
        # Only generate fixtures
        success = generate_fixtures()
        sys.exit(0 if success else 1)

    if "--quick" not in args:
        # Generate fixtures first
        if not generate_fixtures():
            print("\n❌ Fixture generation failed!")
            sys.exit(1)

    # Run tests
    if run_tests():
        print("\n✅ All E2E tests passed!")
        sys.exit(0)
    else:
        print("\n❌ Some E2E tests failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()
