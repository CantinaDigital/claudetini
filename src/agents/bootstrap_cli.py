"""CLI bootstrap tool for creating perfect Claude Code projects.

This is the command-line interface wrapper around BootstrapEngine.
The GUI will use BootstrapEngine directly, but this CLI provides
a simple way to test and validate the bootstrap functionality.

Usage:
    python -m src.agents.bootstrap_cli /path/to/project
    python -m src.agents.bootstrap_cli /path/to/project --dry-run
    python -m src.agents.bootstrap_cli /path/to/project --estimate-cost
"""

import argparse
import sys
from pathlib import Path

from .bootstrap_engine import (
    BootstrapEngine,
    BootstrapResult,
    BootstrapStepType,
)


class BootstrapCLI:
    """CLI wrapper for BootstrapEngine."""

    def __init__(self, project_path: Path, verbose: bool = False):
        self.project_path = project_path
        self.verbose = verbose

    def progress_callback(
        self,
        step_type: BootstrapStepType,
        progress: float,
        message: str,
        step_index: int,
        total_steps: int,
    ) -> None:
        """Display progress with a nice progress bar."""
        # Progress bar
        bar_width = 40
        filled = int(bar_width * progress / 100)
        bar = "█" * filled + "░" * (bar_width - filled)

        # Step indicator
        step_indicator = f"[{step_index}/{total_steps}]"

        # Print with carriage return to overwrite previous line
        print(f"\r{step_indicator} [{bar}] {progress:5.1f}% | {message}", end="", flush=True)

        # New line when complete
        if progress >= 100:
            print()

    def run_bootstrap(
        self,
        skip_git: bool = False,
        skip_architecture: bool = False,
        dry_run: bool = False,
    ) -> BootstrapResult:
        """Run the bootstrap process."""
        try:
            engine = BootstrapEngine(
                project_path=self.project_path,
                progress_callback=self.progress_callback,
            )

            print(f"\n🚀 Bootstrapping project: {self.project_path}")
            if dry_run:
                print("   (DRY RUN - no files will be created)\n")

            result = engine.bootstrap(
                skip_git=skip_git,
                skip_architecture=skip_architecture,
                dry_run=dry_run,
            )

            return result

        except Exception as exc:
            print(f"\n❌ Bootstrap failed: {exc}", file=sys.stderr)
            if self.verbose:
                import traceback

                traceback.print_exc()
            sys.exit(1)

    def estimate_cost(self) -> dict[str, float]:
        """Estimate the cost of bootstrapping this project."""
        try:
            engine = BootstrapEngine(project_path=self.project_path)
            return engine.estimate_cost()
        except Exception as exc:
            print(f"\n❌ Cost estimation failed: {exc}", file=sys.stderr)
            if self.verbose:
                import traceback

                traceback.print_exc()
            sys.exit(1)

    def display_result(self, result: BootstrapResult) -> None:
        """Display the bootstrap result in a nice format."""
        print()  # Blank line after progress

        if result.success:
            print("✅ Bootstrap complete!\n")

            # Show artifacts created
            if result.artifacts:
                print("📄 Created artifacts:")
                for artifact_type, path in result.artifacts.items():
                    # Make path relative to project for cleaner display
                    try:
                        rel_path = path.relative_to(self.project_path)
                    except ValueError:
                        rel_path = path
                    print(f"   • {artifact_type:15} → {rel_path}")

            # Show duration
            print(f"\n⏱️  Completed in {result.duration_seconds:.1f} seconds")

            # Show next steps
            print("\n📋 Next steps:")
            print("   1. Review the generated ROADMAP.md")
            print("   2. Customize CLAUDE.md for your project needs")
            print("   3. Run: claude -p 'Review the roadmap and start with Milestone 1'")

        else:
            print("❌ Bootstrap failed\n")

            if result.errors:
                print("🔴 Errors:")
                for error in result.errors:
                    print(f"   • {error}")

        # Show warnings
        if result.warnings:
            print("\n⚠️  Warnings:")
            for warning in result.warnings:
                print(f"   • {warning}")

        # Show summary
        print(f"\n📊 Summary: {result.steps_completed}/{result.steps_total} steps completed")

    def display_cost_estimate(self, estimate: dict[str, float]) -> None:
        """Display cost estimation in a nice format."""
        print("\n💰 Cost Estimate for Bootstrap\n")
        print(f"   Total steps:     {estimate['steps']}")
        print(f"   Estimated tokens: ~{estimate['total_tokens']:,.0f}")
        print(f"     • Input:        ~{estimate['input_tokens']:,.0f}")
        print(f"     • Output:       ~{estimate['output_tokens']:,.0f}")
        print(f"\n   Estimated cost:  ${estimate['cost_usd']:.2f} USD")
        print("\n   (Actual cost may vary based on project complexity)")


def main() -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Bootstrap a Claude Code project with best practices",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Bootstrap a new project
  python -m src.agents.bootstrap_cli /path/to/project

  # Dry run (show what would be created)
  python -m src.agents.bootstrap_cli /path/to/project --dry-run

  # Estimate cost before running
  python -m src.agents.bootstrap_cli /path/to/project --estimate-cost

  # Skip optional artifacts
  python -m src.agents.bootstrap_cli /path/to/project --skip-architecture

  # Verbose output for debugging
  python -m src.agents.bootstrap_cli /path/to/project -v
        """,
    )

    parser.add_argument(
        "project_path",
        type=Path,
        help="Path to project directory to bootstrap",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be created without actually creating it",
    )

    parser.add_argument(
        "--estimate-cost",
        action="store_true",
        help="Estimate the cost of bootstrapping (doesn't run bootstrap)",
    )

    parser.add_argument(
        "--skip-git",
        action="store_true",
        help="Skip .gitignore generation",
    )

    parser.add_argument(
        "--skip-architecture",
        action="store_true",
        help="Skip architecture documentation",
    )

    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Verbose output for debugging",
    )

    args = parser.parse_args()

    # Validate project path
    if not args.project_path.exists():
        print(f"❌ Error: Project path does not exist: {args.project_path}", file=sys.stderr)
        return 1

    cli = BootstrapCLI(args.project_path, verbose=args.verbose)

    # Handle cost estimation
    if args.estimate_cost:
        estimate = cli.estimate_cost()
        cli.display_cost_estimate(estimate)
        return 0

    # Run bootstrap
    try:
        result = cli.run_bootstrap(
            skip_git=args.skip_git,
            skip_architecture=args.skip_architecture,
            dry_run=args.dry_run,
        )

        cli.display_result(result)

        return 0 if result.success else 1

    except KeyboardInterrupt:
        print("\n\n⚠️  Bootstrap interrupted by user", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"\n❌ Unexpected error: {exc}", file=sys.stderr)
        if args.verbose:
            import traceback

            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
