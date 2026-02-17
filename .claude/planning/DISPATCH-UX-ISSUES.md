# Task Dispatch UX Issues & Solutions

**Date:** 2026-02-15
**Severity:** CRITICAL
**Impact:** App is unusable for task execution

## Executive Summary

The task dispatch flow has **5 critical UX failures** that make the app feel slow, unresponsive, and unreliable:

1. ❌ **Fake progress indicators** - Shows "Waiting for Claude Code to start..." for 26+ seconds when Claude starts instantly
2. ❌ **Generic prompts** - Sends bare minimum context ("Complete the following task: 1.4 Display recently opened...") instead of enriched prompts
3. ❌ **No live output** - Hides actual Claude Code CLI output despite writing it to a file
4. ❌ **No post-execution summary** - Task completes but user has no idea what happened
5. ❌ **No reconciliation** - Task doesn't auto-check when work is done

## Issue 1: Fake Static Messages

### Current Behavior (BAD)
**File:** `app/src/components/dispatch/DispatchOverlay.tsx:224-240`

```typescript
{dispatchOutputTail ? (
  dispatchOutputTail
) : (
  <div>
    Waiting for Claude Code to start...
    {dispatchElapsedSeconds > 30 && (
      <div>Claude is initializing. This can take 30-60 seconds...</div>
    )}
    {dispatchElapsedSeconds > 120 && (
      <div>Still working... Claude may be thinking...</div>
    )}
  </div>
)}
```

**Problem:**
- These are **hardcoded fake messages** based on elapsed time
- `dispatchOutputTail` is never populated because we don't tail the output file
- User sees nothing for 26+ seconds despite Claude Code running immediately

### Root Cause
**File:** `src/agents/dispatcher.py:136-176`

The dispatcher DOES write output to a file in real-time:
```python
with open(output_file, "w", encoding="utf-8") as f:
    while True:
        line = proc.stdout.readline()
        if line:
            output_lines.append(line.rstrip("\n\r"))
            f.write(line)
            f.flush()  # Ensures immediate write
```

But the frontend **never reads this file**!

### Solution

1. **Add output file tailing to frontend**
   - Create `useOutputTail(outputFile)` hook that polls/streams the file
   - Update `DispatchOverlay` to show real output lines
   - Remove all fake messages

2. **Implementation Plan**
   ```typescript
   // New hook: app/src/hooks/useOutputTail.ts
   export function useOutputTail(outputFile: string | null) {
     const [lines, setLines] = useState<string[]>([]);

     useEffect(() => {
       if (!outputFile) return;

       // Poll the output file every 500ms and append new lines
       const interval = setInterval(async () => {
         const newLines = await api.readDispatchOutput(outputFile);
         setLines(newLines);
       }, 500);

       return () => clearInterval(interval);
     }, [outputFile]);

     return lines;
   }
   ```

3. **Backend endpoint needed**
   ```python
   # New endpoint: app/python-sidecar/sidecar/api/routes/dispatch.py
   @router.get("/output/{session_id}")
   async def read_dispatch_output(session_id: str):
       """Read dispatch output file and return lines."""
       output_file = get_dispatch_output_path(session_id)
       if not output_file.exists():
           return {"lines": []}

       lines = output_file.read_text().splitlines()
       return {"lines": lines}
   ```

## Issue 2: Generic Prompts

### Current Behavior (BAD)
**File:** `app/src/components/overview/OverviewTab.tsx:934`

```typescript
const prompt = item.prompt || `Complete the following task: ${item.text}`;
```

**Example output:**
```
Complete the following task: **1.4** Display recently opened projects with last-opened timestamps
```

**Problem:**
- Zero context about the codebase
- No file hints
- No design patterns
- No acceptance criteria
- Claude has to guess where to start

### Solution

Create a **PromptEnricher** that builds context-aware prompts:

```python
# New module: src/core/prompt_enricher.py

class PromptEnricher:
    def __init__(self, project_path: Path):
        self.project = Project.from_path(project_path)
        self.git = GitUtils(project_path)

    def enrich_task_prompt(self, task_text: str, custom_prompt: str | None = None) -> str:
        """Build a context-rich prompt for a roadmap task."""

        # Base task description
        prompt_parts = [custom_prompt or f"Complete the following task: {task_text}"]

        # Add project context from CLAUDE.md
        claude_md = self.project.path / "CLAUDE.md"
        if claude_md.exists():
            conventions = self._extract_conventions(claude_md)
            if conventions:
                prompt_parts.append(f"\n## Code Conventions\n{conventions}")

        # Add relevant file hints
        file_hints = self._find_relevant_files(task_text)
        if file_hints:
            prompt_parts.append(f"\n## Relevant Files\n" + "\n".join(f"- {f}" for f in file_hints))

        # Add component structure hints
        structure = self._infer_component_structure(task_text)
        if structure:
            prompt_parts.append(f"\n## Component Structure\n{structure}")

        # Add acceptance criteria
        criteria = self._generate_acceptance_criteria(task_text)
        if criteria:
            prompt_parts.append(f"\n## Acceptance Criteria\n{criteria}")

        # Add recent changes context
        recent_files = self.git.recently_modified_files(limit=5)
        if recent_files:
            prompt_parts.append(f"\n## Recently Modified Files\n" + "\n".join(f"- {f}" for f in recent_files))

        return "\n".join(prompt_parts)

    def _extract_conventions(self, claude_md: Path) -> str | None:
        """Extract code conventions section from CLAUDE.md."""
        content = claude_md.read_text()
        # Find "Code Conventions" or "Conventions" section
        match = re.search(r'## (?:Code )?Conventions?\s*\n(.*?)(?=\n##|\Z)', content, re.DOTALL)
        if match:
            return match.group(1).strip()[:500]  # Limit to 500 chars
        return None

    def _find_relevant_files(self, task_text: str) -> list[str]:
        """Find files relevant to the task based on keywords."""
        # Extract keywords from task
        keywords = self._extract_keywords(task_text)

        # Search for files matching keywords
        relevant = []
        for keyword in keywords:
            # Use glob patterns based on keyword
            matches = self.project.path.glob(f"**/*{keyword}*")
            relevant.extend(str(m.relative_to(self.project.path)) for m in matches)

        return relevant[:10]  # Limit to top 10

    def _infer_component_structure(self, task_text: str) -> str | None:
        """Infer what component structure is needed based on task."""
        # Look for UI-related keywords
        ui_keywords = ["display", "show", "view", "component", "page", "ui"]
        if any(kw in task_text.lower() for kw in ui_keywords):
            return "This appears to be a UI task. Consider:\n- Component location (src/components/...)\n- Props and state management\n- Styling approach (Tailwind classes)\n- Integration with existing components"

        # Look for API-related keywords
        api_keywords = ["api", "endpoint", "route", "fetch", "request"]
        if any(kw in task_text.lower() for kw in api_keywords):
            return "This appears to be an API task. Consider:\n- Backend route location (python-sidecar/sidecar/api/routes/...)\n- Request/response models\n- Error handling\n- Frontend API client updates (src/api/backend.ts)"

        return None

    def _generate_acceptance_criteria(self, task_text: str) -> str:
        """Generate acceptance criteria for the task."""
        return f"""- Implementation matches the task description
- Code follows project conventions (see CLAUDE.md)
- No regressions in existing functionality
- Code is ready to commit"""

    def _extract_keywords(self, task_text: str) -> list[str]:
        """Extract relevant keywords from task text."""
        # Remove common words and extract meaningful terms
        stop_words = {"the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for"}
        words = re.findall(r'\b\w+\b', task_text.lower())
        return [w for w in words if w not in stop_words and len(w) > 3][:5]
```

**Example enriched prompt:**
```
Complete the following task: **1.4** Display recently opened projects with last-opened timestamps

## Code Conventions
- Use PascalCase for components
- Prefer composition over prop drilling
- Use Zustand for global state
- Tailwind for all styling

## Relevant Files
- src/components/project/ProjectPickerView.tsx
- src/api/backend.ts (getProject endpoint)
- src/types/index.ts (ProjectData interface)

## Component Structure
This appears to be a UI task. Consider:
- Component location (src/components/...)
- Props and state management
- Styling approach (Tailwind classes)
- Integration with existing components

## Acceptance Criteria
- Display timestamp in relative format (e.g., "2h ago")
- Sort projects by last-opened (most recent first)
- Update timestamp on project selection
- Code follows project conventions (see CLAUDE.md)

## Recently Modified Files
- src/components/project/ProjectPickerView.tsx
- app/python-sidecar/sidecar/api/routes/project.py
```

## Issue 3: No Live Output

### Current Problem
Claude Code CLI outputs to stdout/stderr in real-time, but we hide it from the user.

### Solution
**Show actual Claude Code output** - thinking, tool use, file edits, everything!

1. **Parse Claude Code output types:**
   - Thinking blocks: `<thinking>...</thinking>`
   - Tool calls: `<tool_use>...</tool_use>`
   - File operations: "Writing to file:", "Editing file:"
   - Completion: "Task completed"

2. **Render as structured events:**
   ```typescript
   interface CLIEvent {
     type: 'thinking' | 'tool_use' | 'file_edit' | 'message' | 'error';
     content: string;
     timestamp: number;
   }

   function parseCLIOutput(lines: string[]): CLIEvent[] {
     // Parse output into structured events
     // Show thinking as collapsible sections
     // Highlight file operations
     // Show errors prominently
   }
   ```

## Issue 4: No Post-Execution Summary

### Current Problem
Task completes, overlay closes, user has **no idea what happened**.

### Solution

Add **post-dispatch summary view** with:

1. **What was accomplished?**
   - Use git diff to list changed files
   - Count lines added/removed
   - Parse Claude's final message for summary

2. **Files Changed**
   ```
   ✓ Task completed successfully

   Files Changed (3):
   - src/components/project/ProjectPickerView.tsx (+45, -12)
   - src/api/backend.ts (+8, -0)
   - src/types/index.ts (+3, -0)

   Total: +56 lines, -12 lines
   ```

3. **Actions**
   - [Review Changes] - Opens git diff view
   - [Mark Task Complete] - Checks off in roadmap
   - [Commit Changes] - Opens commit dialog
   - [Run Again] - Retry if needed

## Issue 5: No Reconciliation

### Current Problem
Task runs, makes changes, but **never auto-checks** in the roadmap.

### Solution

Add **reconciliation agent** that:

1. **Analyzes git changes** after dispatch completes
2. **Compares to task requirements** using the enriched prompt
3. **Offers to mark complete** if changes match expectations

```python
# New module: src/agents/reconciliation_agent.py

class ReconciliationAgent:
    def analyze_dispatch_result(
        self,
        task_text: str,
        git_changes: list[str],
        dispatch_output: str
    ) -> ReconciliationResult:
        """Analyze if the dispatch accomplished the task."""

        # Check if files were modified
        if not git_changes:
            return ReconciliationResult(
                confidence=0.0,
                recommendation="no_action",
                reason="No files were changed"
            )

        # Look for success indicators in output
        success_indicators = [
            "task completed",
            "successfully",
            "done",
            "finished"
        ]

        output_lower = dispatch_output.lower()
        has_success = any(ind in output_lower for ind in success_indicators)

        # Look for error indicators
        error_indicators = ["error", "failed", "exception"]
        has_errors = any(err in output_lower for err in error_indicators)

        if has_errors:
            return ReconciliationResult(
                confidence=0.2,
                recommendation="review_needed",
                reason="Output contains error indicators"
            )

        if has_success and git_changes:
            return ReconciliationResult(
                confidence=0.9,
                recommendation="mark_complete",
                reason=f"Task appears complete: {len(git_changes)} files changed"
            )

        return ReconciliationResult(
            confidence=0.5,
            recommendation="review_needed",
            reason="Changes made but unclear if task is complete"
        )
```

## Implementation Priority

### Phase 1: Live Output (IMMEDIATE)
1. Add `/api/dispatch/output/{session_id}` endpoint
2. Create `useOutputTail` hook
3. Replace fake messages with real output
4. **Impact:** Users see Claude working immediately

### Phase 2: Enriched Prompts (HIGH)
1. Implement `PromptEnricher` class
2. Add `/api/dispatch/enrich-prompt` endpoint
3. Update `OverviewTab` to enrich before dispatch
4. **Impact:** Claude gets better context, higher success rate

### Phase 3: Post-Dispatch Summary (HIGH)
1. Add git diff analysis after completion
2. Create summary view component
3. Add action buttons (Review, Mark Complete, Commit)
4. **Impact:** Users know what happened, can take next steps

### Phase 4: Reconciliation (MEDIUM)
1. Implement `ReconciliationAgent`
2. Auto-analyze after dispatch
3. Offer to mark tasks complete
4. **Impact:** Automated progress tracking

## Acceptance Criteria

- [ ] User sees Claude Code output within 1 second of clicking "Start"
- [ ] No more fake "Waiting for Claude Code to start..." messages
- [ ] Prompts include file hints, conventions, and acceptance criteria
- [ ] After completion, user sees summary of files changed
- [ ] Tasks auto-check when reconciliation confirms success
- [ ] Overall dispatch flow feels fast, transparent, and reliable

## Next Steps

1. Add Milestone 12 to ROADMAP.md ✅
2. Create `/plan-phase` for detailed implementation plan
3. Execute Phase 1 (Live Output) first for immediate impact
4. Test with real tasks from current milestones
5. Iterate based on feedback
