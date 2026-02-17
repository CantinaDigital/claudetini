# Testing Guide - Bootstrap Engine

**Quick start guide for testing the newly refactored Bootstrap Engine**

## Prerequisites

1. **Claude CLI installed**:
   ```bash
   which claude  # Should return path to claude binary
   claude --version  # Should show version info
   ```

2. **Claudetini repository**:
   ```bash
   cd /path/to/claudetini
   ```

## Test 1: Cost Estimation (No execution, instant)

**Purpose**: Verify cost estimation works

```bash
# Create a test directory
mkdir -p ~/bootstrap-test-1
cd ~/bootstrap-test-1
echo "# Test Project" > README.md

# Estimate cost
python -m src.agents.bootstrap_cli ~/bootstrap-test-1 --estimate-cost
```

**Expected output**:
```
💰 Cost Estimate for Bootstrap

   Total steps:     5
   Estimated tokens: ~260,000
     • Input:        ~156,000
     • Output:       ~104,000

   Estimated cost:  $0.34 USD

   (Actual cost may vary based on project complexity)
```

**Success criteria**: ✅ Shows cost estimate without errors

---

## Test 2: Dry Run (No execution, instant)

**Purpose**: Verify bootstrap steps are configured correctly

```bash
python -m src.agents.bootstrap_cli ~/bootstrap-test-1 --dry-run
```

**Expected output**:
```
🚀 Bootstrapping project: /Users/[you]/bootstrap-test-1
   (DRY RUN - no files will be created)

[1/5] [████████████████████████████████████████]  20.0% | Analyzing project structure
[2/5] [████████████████████████████████████████]  50.0% | Generating roadmap
[3/5] [████████████████████████████████████████]  80.0% | Creating CLAUDE.md
[4/5] [████████████████████████████████████████]  95.0% | Creating .gitignore
[5/5] [████████████████████████████████████████] 100.0% | Documenting architecture

✅ Bootstrap complete!

📄 Created artifacts:
   • analyze        → .bootstrap_analysis.md
   • roadmap        → .claude/planning/ROADMAP.md
   • claude_md      → CLAUDE.md
   • gitignore      → .gitignore
   • architecture   → docs/ARCHITECTURE.md

⏱️  Completed in 0.0 seconds
```

**Success criteria**: ✅ Shows all 5 steps without errors

---

## Test 3: Real Bootstrap on Empty Project (EXECUTES CLAUDE CODE)

**Purpose**: Validate bootstrap on a brand new project

**⚠️ Cost**: ~$0.30-0.40 per run

```bash
# Create empty project
mkdir -p ~/bootstrap-test-empty
cd ~/bootstrap-test-empty

# Run bootstrap
python -m src.agents.bootstrap_cli ~/bootstrap-test-empty
```

**Expected behavior**:
1. Shows progress bar for each step
2. Takes 3-8 minutes total
3. Creates 5 files:
   - `.claude/planning/ROADMAP.md`
   - `CLAUDE.md`
   - `.gitignore`
   - `docs/ARCHITECTURE.md`
   - `.bootstrap_analysis.md` (temp file)

**Success criteria**:
- [ ] All files created successfully
- [ ] ROADMAP.md has milestone structure with checkboxes
- [ ] CLAUDE.md has sections: Overview, Architecture, Conventions, Commands
- [ ] .gitignore has generic patterns (OS, editors, etc.)
- [ ] ARCHITECTURE.md explains project structure
- [ ] No errors or exceptions

**Validation**:
```bash
# Check files were created
ls -la ~/bootstrap-test-empty/.claude/planning/ROADMAP.md
ls -la ~/bootstrap-test-empty/CLAUDE.md
ls -la ~/bootstrap-test-empty/.gitignore
ls -la ~/bootstrap-test-empty/docs/ARCHITECTURE.md

# Read the generated roadmap
cat ~/bootstrap-test-empty/.claude/planning/ROADMAP.md

# Read the CLAUDE.md
cat ~/bootstrap-test-empty/CLAUDE.md
```

---

## Test 4: Real Bootstrap on Python Project (EXECUTES CLAUDE CODE)

**Purpose**: Validate project-specific artifact generation

**⚠️ Cost**: ~$0.30-0.40 per run

```bash
# Create a simple Python project
mkdir -p ~/bootstrap-test-python
cd ~/bootstrap-test-python

# Add some Python files
cat > main.py << 'EOF'
"""Simple Flask API"""
from flask import Flask, jsonify

app = Flask(__name__)

@app.route('/api/health')
def health():
    return jsonify({"status": "ok"})

if __name__ == '__main__':
    app.run(debug=True)
EOF

cat > requirements.txt << 'EOF'
flask==3.0.0
pytest==7.4.0
EOF

# Run bootstrap
python -m src.agents.bootstrap_cli ~/bootstrap-test-python
```

**Success criteria**:
- [ ] ROADMAP.md mentions Python/Flask specifically
- [ ] CLAUDE.md has Python code conventions (snake_case, etc.)
- [ ] .gitignore has Python patterns (__pycache__, *.pyc, venv/, etc.)
- [ ] ARCHITECTURE.md describes Flask API architecture
- [ ] Milestones are relevant to a Flask API project

**Validation**:
```bash
# Check that .gitignore has Python patterns
grep -i "pycache" ~/bootstrap-test-python/.gitignore
grep -i "venv" ~/bootstrap-test-python/.gitignore

# Check that CLAUDE.md mentions Python
grep -i "python" ~/bootstrap-test-python/CLAUDE.md

# Check that ROADMAP mentions Flask
grep -i "flask" ~/bootstrap-test-python/.claude/planning/ROADMAP.md
```

---

## Test 5: Bootstrap on Existing JavaScript Project (EXECUTES CLAUDE CODE)

**Purpose**: Validate bootstrap on a different language

**⚠️ Cost**: ~$0.30-0.40 per run

```bash
# Create a React project structure
mkdir -p ~/bootstrap-test-react/src
cd ~/bootstrap-test-react

# Add package.json
cat > package.json << 'EOF'
{
  "name": "my-react-app",
  "version": "1.0.0",
  "scripts": {
    "dev": "vite",
    "build": "vite build"
  },
  "dependencies": {
    "react": "^19.0.0",
    "react-dom": "^19.0.0"
  },
  "devDependencies": {
    "vite": "^5.0.0"
  }
}
EOF

# Add a React component
cat > src/App.jsx << 'EOF'
import { useState } from 'react'

export default function App() {
  const [count, setCount] = useState(0)

  return (
    <div>
      <h1>Counter: {count}</h1>
      <button onClick={() => setCount(count + 1)}>Increment</button>
    </div>
  )
}
EOF

# Run bootstrap
python -m src.agents.bootstrap_cli ~/bootstrap-test-react
```

**Success criteria**:
- [ ] ROADMAP.md mentions React/Vite specifically
- [ ] CLAUDE.md has JavaScript conventions (camelCase, etc.)
- [ ] .gitignore has Node.js patterns (node_modules/, dist/, .env, etc.)
- [ ] ARCHITECTURE.md describes React component architecture
- [ ] Milestones relevant to React app development

**Validation**:
```bash
# Check .gitignore has Node.js patterns
grep -i "node_modules" ~/bootstrap-test-react/.gitignore
grep -i "dist" ~/bootstrap-test-react/.gitignore

# Check CLAUDE.md mentions React
grep -i "react" ~/bootstrap-test-react/CLAUDE.md

# Check ROADMAP mentions React/Vite
grep -iE "(react|vite)" ~/bootstrap-test-react/.claude/planning/ROADMAP.md
```

---

## Test 6: Skip Optional Artifacts

**Purpose**: Verify --skip flags work

```bash
mkdir -p ~/bootstrap-test-minimal
cd ~/bootstrap-test-minimal

# Skip architecture docs
python -m src.agents.bootstrap_cli ~/bootstrap-test-minimal --skip-architecture

# Verify architecture doc was NOT created
ls ~/bootstrap-test-minimal/docs/ARCHITECTURE.md  # Should fail
```

**Success criteria**:
- [ ] ROADMAP.md and CLAUDE.md created
- [ ] docs/ARCHITECTURE.md NOT created
- [ ] Shows warning about skipped step

---

## Test 7: Existing .gitignore (Should skip)

**Purpose**: Verify skip-if-exists logic

```bash
mkdir -p ~/bootstrap-test-existing
cd ~/bootstrap-test-existing

# Create existing .gitignore
echo "*.log" > .gitignore

# Run bootstrap
python -m src.agents.bootstrap_cli ~/bootstrap-test-existing

# Verify .gitignore was NOT overwritten
cat .gitignore  # Should only contain "*.log"
```

**Success criteria**:
- [ ] .gitignore still only has "*.log"
- [ ] Shows warning: "Skipped .gitignore (already exists)"

---

## Test 8: Error Handling (Invalid path)

**Purpose**: Verify graceful error handling

```bash
# Try to bootstrap non-existent path
python -m src.agents.bootstrap_cli /does/not/exist
```

**Expected output**:
```
❌ Error: Project path does not exist: /does/not/exist
```

**Success criteria**: ✅ Shows clear error message, doesn't crash

---

## Success Metrics

After running all tests, verify:

1. **Success Rate**: 80%+ of real bootstrap runs complete successfully
2. **Quality**: Generated artifacts are project-specific (not generic templates)
3. **Speed**: Average completion time < 10 minutes
4. **Reliability**: No unhandled exceptions or crashes

## Clean Up Test Directories

```bash
# Remove all test directories
rm -rf ~/bootstrap-test-*
```

---

## Next Steps After Validation

Once bootstrap engine passes all tests:

1. ✅ Mark "Test BootstrapEngine on 3 real projects" as complete
2. 🚀 Proceed to **Phase 1 Week 5-6**: Build Readiness Scorecard Engine
3. 📝 Document any issues or improvements needed
4. 🎯 Prepare for GUI integration in Phase 2

---

**Created**: 2026-02-14
**Status**: Ready for testing
**Estimated testing time**: 30-60 minutes (including execution time)
**Estimated cost**: $1.50-2.00 (for real execution tests)
