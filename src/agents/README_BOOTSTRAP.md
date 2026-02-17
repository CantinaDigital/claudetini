# Bootstrap CLI

**Phase 1, Week 1-4: Technical validation for Claudetini**

## Purpose

This CLI tool validates the technical feasibility of automated project bootstrapping before building the GUI. It creates perfect Claude Code project setups by:

1. Analyzing existing projects
2. Generating milestone-based roadmaps (ROADMAP.md)
3. Creating project-specific instructions (CLAUDE.md)
4. Setting up sensible defaults (.gitignore)
5. Documenting architecture (docs/ARCHITECTURE.md)

## Installation

```bash
# Ensure Claude CLI is installed and in PATH
which claude  # Should return path to claude binary

# No additional installation needed - runs directly from source
cd /path/to/claudetini
```

## Usage

### Basic Bootstrap

```bash
python -m src.agents.bootstrap_cli /path/to/your/project
```

### Dry Run (Preview Only)

```bash
python -m src.agents.bootstrap_cli /path/to/your/project --dry-run
```

### Skip Optional Artifacts

```bash
# Skip .gitignore
python -m src.agents.bootstrap_cli /path/to/your/project --skip-git

# Skip architecture docs
python -m src.agents.bootstrap_cli /path/to/your/project --skip-architecture

# Skip both
python -m src.agents.bootstrap_cli /path/to/your/project --skip-git --skip-architecture
```

### Verbose Output

```bash
python -m src.agents.bootstrap_cli /path/to/your/project -v
```

## Validation Plan (Week 1-4)

### Week 1-2: Test on 3 Project Types

1. **Python project** (existing codebase)
   ```bash
   python -m src.agents.bootstrap_cli ~/projects/my-python-app
   ```

2. **JavaScript/Node.js project** (existing codebase)
   ```bash
   python -m src.agents.bootstrap_cli ~/projects/my-react-app
   ```

3. **Rust project** (existing codebase)
   ```bash
   python -m src.agents.bootstrap_cli ~/projects/my-rust-cli
   ```

### Week 3: Edge Cases

4. **Empty directory** (new project)
   ```bash
   mkdir ~/projects/new-project
   python -m src.agents.bootstrap_cli ~/projects/new-project
   ```

5. **Monorepo** (complex structure)
   ```bash
   python -m src.agents.bootstrap_cli ~/projects/monorepo
   ```

### Week 4: Validation Criteria

For each test project, verify:

- [ ] ROADMAP.md is created with valid milestone structure
- [ ] ROADMAP.md tasks are specific to the project (not generic)
- [ ] CLAUDE.md contains project-specific conventions
- [ ] .gitignore includes language-specific patterns
- [ ] docs/ARCHITECTURE.md explains actual architecture
- [ ] All files are readable and well-formatted
- [ ] Process completes in < 10 minutes
- [ ] No API errors or timeouts

## Success Metrics

**Must achieve before proceeding to GUI:**

1. **Success rate**: 80%+ completion rate across 5+ test projects
2. **Quality**: Manual review confirms artifacts are project-specific (not generic)
3. **Speed**: Average completion time < 5 minutes
4. **Reliability**: No crashes or unhandled exceptions

## Integration with GUI (Phase 2)

Once validated, this CLI becomes the backend for the GUI wizard:

```python
# GUI calls bootstrap_cli.py as a library
from src.agents.bootstrap_cli import BootstrapCLI, BootstrapConfig

def on_bootstrap_button_click():
    config = BootstrapConfig(
        project_path=selected_project_path,
        dry_run=False,
    )

    def progress_callback(step, progress, message):
        # Update GUI progress bar
        update_ui(step, progress, message)

    cli = BootstrapCLI(config, progress_callback=progress_callback)
    artifacts = cli.bootstrap()
    # Show completion screen
```

## Example Output

```
[████████████████████████████████████████] 100.0% | complete       | Bootstrap complete!

✅ Bootstrap complete!

Created artifacts:
  • roadmap        → /path/to/project/.claude/planning/ROADMAP.md
  • claude_md      → /path/to/project/CLAUDE.md
  • gitignore      → /path/to/project/.gitignore
  • architecture   → /path/to/project/docs/ARCHITECTURE.md

Next steps:
  1. Review the generated ROADMAP.md
  2. Customize CLAUDE.md for your project
  3. Run: claude -p 'Review the roadmap and start with Milestone 1'
```

## Troubleshooting

### "Claude CLI not found"

Ensure Claude Code is installed:
```bash
# Install Claude CLI (if not already installed)
# Follow: https://docs.anthropic.com/claude/docs/install-claude-code

# Verify installation
claude --version
```

### "Project path does not exist"

Ensure the path is valid:
```bash
# Create directory first if needed
mkdir -p /path/to/your/project
python -m src.agents.bootstrap_cli /path/to/your/project
```

### "Roadmap file not created"

This means Claude Code ran but didn't create the expected file. Possible causes:

1. Claude Code API error (check output)
2. File permission issues
3. Invalid project path

Run with `--dry-run` first to test without actually creating files.

### Timeout Errors

If bootstrapping times out (> 10 minutes per artifact):

1. Check internet connection
2. Verify Claude CLI is authenticated (`claude --help`)
3. Try with smaller project first
4. Check Claude Code API status

## Cost Estimation

**Per bootstrap run:**

- Approximate tokens: 50k-100k (depends on project size)
- Approximate cost: $0.15-$0.30 (using Claude Sonnet)
- Time: 3-8 minutes

**For validation testing (5 projects):**

- Total cost: ~$1-2
- Total time: 15-40 minutes

## Next Phase: GUI Integration

After CLI validation succeeds, proceed to:

1. **Phase 1 Week 3-4**: Build `BootstrapEngine` (refactor CLI into reusable library)
2. **Phase 1 Week 5-6**: Build `ReadinessScanner` (detect what's missing)
3. **Phase 2 Month 3**: Build GUI wizard around validated CLI

---

**Status**: ✅ Ready for testing
**Last Updated**: 2026-02-13
**Owner**: Claudetini Team
