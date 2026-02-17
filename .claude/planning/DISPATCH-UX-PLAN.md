# Task Dispatch UX Overhaul - Implementation Plan

**Goal:** Fix 5 critical UX failures in task dispatch flow
**Total Effort:** ~12-16 hours across 4 phases
**Priority:** CRITICAL - App currently unusable for task execution

---

## Phase 1: Live Output Streaming (IMMEDIATE)
**Effort:** 2-3 hours | **Impact:** 🔥 HIGH - Users see Claude working immediately

### Objective
Replace fake "Waiting for Claude Code to start..." messages with real-time CLI output tailing.

### Files to Create

#### 1. Backend: Output File Reader
**File:** `app/python-sidecar/sidecar/api/routes/dispatch.py`

Add new endpoint:
```python
@router.get("/output/{session_id}")
async def read_dispatch_output(session_id: str):
    """Read dispatch output file and return lines.

    Allows frontend to tail the output file that dispatcher.py writes to.
    Returns all lines each time (frontend tracks what it's already seen).
    """
    try:
        from src.agents.dispatcher import get_dispatch_output_path
        from pathlib import Path

        # Get the output file path for this session
        session_id_clean = session_id.replace(".log", "")
        _, output_file = get_dispatch_output_path(Path.cwd(), session_id_clean)

        if not output_file.exists():
            return {"lines": [], "exists": False}

        # Read all lines
        lines = output_file.read_text(encoding="utf-8", errors="ignore").splitlines()

        return {
            "lines": lines,
            "exists": True,
            "line_count": len(lines)
        }
    except Exception as e:
        logger.error(f"Failed to read dispatch output: {e}")
        return {"lines": [], "exists": False, "error": str(e)}
```

**Why this approach:**
- Simple polling (500ms intervals)
- Returns all lines each time (frontend diffs to find new ones)
- Handles file not existing yet (dispatch starting up)
- Error resilient

#### 2. Frontend: Output Tail Hook
**File:** `app/src/hooks/useOutputTail.ts` (NEW)

```typescript
import { useState, useEffect, useRef } from 'react';
import { api } from '../api/backend';

interface UseOutputTailOptions {
  /** Polling interval in ms (default: 500) */
  interval?: number;
  /** Max lines to keep in memory (default: 1000) */
  maxLines?: number;
}

/**
 * Hook to tail a dispatch output file in real-time.
 *
 * Polls the backend every 500ms for new lines and appends them.
 * Stops polling when outputFile becomes null (dispatch ended).
 */
export function useOutputTail(
  outputFile: string | null,
  options: UseOutputTailOptions = {}
) {
  const { interval = 500, maxLines = 1000 } = options;
  const [lines, setLines] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const lastLineCount = useRef(0);

  useEffect(() => {
    if (!outputFile) {
      // Clear lines when output file is null (dispatch not running)
      setLines([]);
      lastLineCount.current = 0;
      return;
    }

    setIsLoading(true);
    let cancelled = false;

    const pollOutput = async () => {
      try {
        // Extract session_id from output file path
        const sessionId = outputFile.split('/').pop()?.replace('.log', '') || '';
        const result = await api.readDispatchOutput(sessionId);

        if (cancelled) return;

        if (result.exists && result.lines.length > lastLineCount.current) {
          // New lines available - append them
          const newLines = result.lines.slice(lastLineCount.current);
          setLines((prev) => [...prev, ...newLines].slice(-maxLines));
          lastLineCount.current = result.lines.length;
        }

        setIsLoading(false);
      } catch (error) {
        console.error('Failed to tail output:', error);
        setIsLoading(false);
      }
    };

    // Poll immediately, then on interval
    pollOutput();
    const intervalId = setInterval(pollOutput, interval);

    return () => {
      cancelled = true;
      clearInterval(intervalId);
    };
  }, [outputFile, interval, maxLines]);

  return { lines, isLoading };
}
```

**Why this approach:**
- Tracks last line count to only append new lines (efficient)
- Cleans up when dispatch ends (outputFile becomes null)
- Limits memory usage (keeps last 1000 lines)
- Polls immediately on mount for fast initial display

#### 3. Backend API Client
**File:** `app/src/api/backend.ts`

Add method to api object (around line 340):
```typescript
readDispatchOutput: (sessionId: string) =>
  fetchApi<{
    lines: string[];
    exists: boolean;
    line_count?: number;
    error?: string;
  }>(`/api/dispatch/output/${encodeURIComponent(sessionId)}`),
```

#### 4. Frontend: Update Dispatch Overlay
**File:** `app/src/components/dispatch/DispatchOverlay.tsx`

Replace lines 194-242 with:
```typescript
import { useOutputTail } from '../../hooks/useOutputTail';

// At top of component:
const { lines: outputLines } = useOutputTail(dispatchLogFile);

// Replace the entire "Live CLI output" section:
{isDispatching && !isStreaming && (
  <div
    style={{
      fontSize: 10,
      fontFamily: "JetBrains Mono, monospace",
      color: t.text2,
      background: t.surface0,
      border: `1px solid ${t.border0}`,
      borderRadius: 8,
      padding: "8px 10px",
      textAlign: "left",
      whiteSpace: "pre-wrap",
      marginBottom: 10,
      maxHeight: 200,
      overflowY: "auto",
    }}
  >
    <div
      style={{
        fontSize: 9,
        color: t.text3,
        marginBottom: 6,
        textTransform: "uppercase",
        letterSpacing: "0.5px",
        fontWeight: 700,
      }}
    >
      Live Output
    </div>
    {outputLines.length > 0 ? (
      <div>
        {outputLines.slice(-20).map((line, i) => (
          <div key={i} style={{ marginBottom: 2 }}>
            {line}
          </div>
        ))}
      </div>
    ) : (
      <div style={{ fontStyle: "italic", color: t.text3 }}>
        Connecting to Claude Code...
      </div>
    )}
  </div>
)}
```

**Key changes:**
- ❌ Remove all fake time-based messages
- ✅ Use `useOutputTail` hook
- ✅ Show last 20 lines of real output
- ✅ Simple "Connecting..." message only when no output yet

### Files to Modify

1. `app/python-sidecar/sidecar/api/routes/dispatch.py` - Add endpoint
2. `app/src/api/backend.ts` - Add API method
3. `app/src/components/dispatch/DispatchOverlay.tsx` - Use hook, remove fake messages

### Testing Checklist

- [ ] Start a task from Overview tab
- [ ] See "Connecting..." message for <1 second
- [ ] See real Claude Code output within 1-2 seconds
- [ ] Output updates as Claude works (polling every 500ms)
- [ ] No fake "Waiting..." or "Initializing..." messages
- [ ] Output scrolls automatically to show latest
- [ ] Overlay closes cleanly when task completes

### Acceptance Criteria

✅ User sees real CLI output within 1 second of clicking "Start"
✅ No more fake time-based messages
✅ Output updates in near real-time (500ms polling)

---

## Phase 2: Enriched Task Prompts (HIGH)
**Effort:** 4-5 hours | **Impact:** 🔥 HIGH - Better context = higher success rate

### Objective
Replace generic "Complete the following task: X" prompts with context-rich prompts that include file hints, conventions, and acceptance criteria.

### Files to Create

#### 1. Core: Prompt Enricher
**File:** `src/core/prompt_enricher.py` (NEW)

```python
"""Context-aware prompt enrichment for task dispatch."""

import re
from pathlib import Path
from dataclasses import dataclass

from .project import Project
from .git_utils import GitUtils


@dataclass
class EnrichedPrompt:
    """Enriched prompt with context."""
    prompt: str
    context_added: list[str]  # List of context types added: "conventions", "files", "structure", etc.


class PromptEnricher:
    """Enriches task prompts with project context."""

    def __init__(self, project_path: Path):
        self.project = Project.from_path(project_path)
        self.git = GitUtils(project_path)

    def enrich_task_prompt(
        self,
        task_text: str,
        custom_prompt: str | None = None
    ) -> EnrichedPrompt:
        """Build a context-rich prompt for a roadmap task.

        Args:
            task_text: The task description from roadmap
            custom_prompt: Optional custom prompt (if set in roadmap item)

        Returns:
            EnrichedPrompt with added context
        """
        prompt_parts = [custom_prompt or f"Complete the following task: {task_text}"]
        context_added = []

        # 1. Add code conventions from CLAUDE.md
        conventions = self._extract_conventions()
        if conventions:
            prompt_parts.append(f"\n## Code Conventions\n{conventions}")
            context_added.append("conventions")

        # 2. Add relevant file hints
        file_hints = self._find_relevant_files(task_text)
        if file_hints:
            prompt_parts.append(
                f"\n## Relevant Files\n" + "\n".join(f"- {f}" for f in file_hints)
            )
            context_added.append("file_hints")

        # 3. Add component structure guidance
        structure = self._infer_component_structure(task_text)
        if structure:
            prompt_parts.append(f"\n## Component Structure Guidance\n{structure}")
            context_added.append("structure")

        # 4. Add acceptance criteria
        criteria = self._generate_acceptance_criteria(task_text)
        prompt_parts.append(f"\n## Acceptance Criteria\n{criteria}")
        context_added.append("acceptance_criteria")

        # 5. Add recent changes context
        recent_files = self._get_recent_changes()
        if recent_files:
            prompt_parts.append(
                f"\n## Recently Modified Files\n" + "\n".join(f"- {f}" for f in recent_files)
            )
            context_added.append("recent_changes")

        return EnrichedPrompt(
            prompt="\n".join(prompt_parts),
            context_added=context_added
        )

    def _extract_conventions(self) -> str | None:
        """Extract code conventions section from CLAUDE.md."""
        claude_md = self.project.path / "CLAUDE.md"
        if not claude_md.exists():
            return None

        try:
            content = claude_md.read_text(encoding="utf-8")
            # Find "Code Conventions" or "Conventions" section
            match = re.search(
                r'## (?:Code )?Conventions?\s*\n(.*?)(?=\n##|\Z)',
                content,
                re.DOTALL | re.IGNORECASE
            )
            if match:
                conventions = match.group(1).strip()
                # Limit to 600 chars to avoid bloating prompt
                return conventions[:600] + ("..." if len(conventions) > 600 else "")
        except Exception:
            pass

        return None

    def _find_relevant_files(self, task_text: str) -> list[str]:
        """Find files relevant to the task based on keywords."""
        keywords = self._extract_keywords(task_text)
        if not keywords:
            return []

        relevant = set()
        for keyword in keywords:
            # Search for files with keyword in name
            try:
                matches = list(self.project.path.glob(f"**/*{keyword}*"))
                # Filter out common noise (node_modules, .git, etc.)
                matches = [
                    m for m in matches
                    if not any(
                        part.startswith('.')
                        or part in ('node_modules', 'dist', 'build', '__pycache__')
                        for part in m.parts
                    )
                ]
                for match in matches[:3]:  # Top 3 per keyword
                    try:
                        rel_path = match.relative_to(self.project.path)
                        relevant.add(str(rel_path))
                    except ValueError:
                        continue
            except Exception:
                continue

        return sorted(list(relevant))[:10]  # Max 10 files

    def _infer_component_structure(self, task_text: str) -> str | None:
        """Infer what component structure is needed based on task."""
        task_lower = task_text.lower()

        # UI-related task
        ui_keywords = ["display", "show", "view", "component", "page", "ui", "button", "form"]
        if any(kw in task_lower for kw in ui_keywords):
            return """This appears to be a UI task. Consider:
- Component location: src/components/... or app/src/components/...
- Props and state management (useState, Zustand)
- Styling approach (Tailwind CSS classes)
- Integration with existing components"""

        # API-related task
        api_keywords = ["api", "endpoint", "route", "fetch", "request", "backend"]
        if any(kw in task_lower for kw in api_keywords):
            return """This appears to be an API task. Consider:
- Backend route: python-sidecar/sidecar/api/routes/...
- Request/response models (Pydantic)
- Error handling and status codes
- Frontend API client: app/src/api/backend.ts"""

        # Core logic task
        core_keywords = ["parser", "scanner", "analyzer", "engine", "core", "utils"]
        if any(kw in task_lower for kw in core_keywords):
            return """This appears to be a core logic task. Consider:
- Module location: src/core/...
- Type hints and dataclasses
- Unit tests in tests/...
- Error handling and edge cases"""

        return None

    def _generate_acceptance_criteria(self, task_text: str) -> str:
        """Generate acceptance criteria for the task."""
        return """- Implementation matches the task description exactly
- Code follows project conventions (see CLAUDE.md)
- No regressions in existing functionality
- Changes are ready to commit (no debug code, proper formatting)"""

    def _get_recent_changes(self) -> list[str]:
        """Get recently modified files from git."""
        try:
            # Get files modified in last 3 commits
            result = self.git.run_git_command(
                ["log", "--name-only", "--pretty=format:", "-3"]
            )
            if result.success and result.stdout:
                files = [
                    line.strip()
                    for line in result.stdout.strip().split('\n')
                    if line.strip()
                ]
                # Deduplicate and limit
                return list(dict.fromkeys(files))[:5]
        except Exception:
            pass

        return []

    def _extract_keywords(self, task_text: str) -> list[str]:
        """Extract relevant keywords from task text."""
        # Remove markdown and common words
        stop_words = {
            "the", "a", "an", "and", "or", "but", "in", "on", "at",
            "to", "for", "of", "with", "from", "by", "as", "is", "are"
        }

        # Extract words
        words = re.findall(r'\b[a-zA-Z_-]+\b', task_text.lower())

        # Filter and return top 5 meaningful keywords
        keywords = [
            w for w in words
            if w not in stop_words and len(w) > 3
        ]

        return keywords[:5]
```

#### 2. Backend: Enrich Endpoint
**File:** `app/python-sidecar/sidecar/api/routes/dispatch.py`

Add endpoint:
```python
from pydantic import BaseModel

class EnrichPromptRequest(BaseModel):
    task_text: str
    custom_prompt: str | None = None
    project_path: str

class EnrichPromptResponse(BaseModel):
    enriched_prompt: str
    context_added: list[str]

@router.post("/enrich-prompt")
async def enrich_prompt(request: EnrichPromptRequest):
    """Enrich a task prompt with project context."""
    try:
        from src.core.prompt_enricher import PromptEnricher
        from pathlib import Path

        enricher = PromptEnricher(Path(request.project_path))
        result = enricher.enrich_task_prompt(
            task_text=request.task_text,
            custom_prompt=request.custom_prompt
        )

        return EnrichPromptResponse(
            enriched_prompt=result.prompt,
            context_added=result.context_added
        )
    except Exception as e:
        logger.error(f"Failed to enrich prompt: {e}")
        # Fallback to basic prompt if enrichment fails
        basic = request.custom_prompt or f"Complete the following task: {request.task_text}"
        return EnrichPromptResponse(
            enriched_prompt=basic,
            context_added=[]
        )
```

#### 3. Frontend: API Client
**File:** `app/src/api/backend.ts`

Add method:
```typescript
enrichPrompt: (
  projectId: string,
  taskText: string,
  customPrompt?: string
) =>
  fetchApi<{
    enriched_prompt: string;
    context_added: string[];
  }>("/api/dispatch/enrich-prompt", {
    method: "POST",
    body: JSON.stringify({
      project_path: projectId,
      task_text: taskText,
      custom_prompt: customPrompt,
    }),
  }),
```

#### 4. Frontend: Use in Overview Tab
**File:** `app/src/components/overview/OverviewTab.tsx`

Modify `handleStartSession` function (around line 473):
```typescript
const handleStartSession = async (prompt?: string, itemRef?: { text: string; prompt?: string }) => {
  // NEW: Enrich the prompt before dispatching
  let finalPrompt = prompt || "Continue work on the current task";

  if (itemRef && projectPath) {
    try {
      const enriched = await api.enrichPrompt(
        projectPath,
        itemRef.text,
        itemRef.prompt
      );
      finalPrompt = enriched.enriched_prompt;
      console.log('Context added:', enriched.context_added);
    } catch (error) {
      console.warn('Failed to enrich prompt, using basic version:', error);
      // Fallback to basic prompt
      finalPrompt = itemRef.prompt || `Complete the following task: ${itemRef.text}`;
    }
  }

  const source: DispatchContext["source"] = itemRef ? "task" : "overview";
  setDispatchContext({ prompt: finalPrompt, mode: dispatchMode, source, itemRef });

  if (onShowPreFlight) {
    onShowPreFlight(finalPrompt, dispatchMode, source, itemRef);
  } else {
    onStart?.(finalPrompt, dispatchMode);
  }
};
```

### Files to Modify

1. `app/src/components/overview/OverviewTab.tsx` - Enrich before dispatch
2. `app/src/api/backend.ts` - Add enrichPrompt method
3. `app/python-sidecar/sidecar/api/routes/dispatch.py` - Add endpoint

### Testing Checklist

- [ ] Click "Start" on a task
- [ ] Check console for "Context added: [...]"
- [ ] Verify enriched prompt in PreFlight modal contains:
  - [ ] Code conventions from CLAUDE.md
  - [ ] Relevant file hints
  - [ ] Component structure guidance
  - [ ] Acceptance criteria
  - [ ] Recent changes (if available)
- [ ] Test with task that has custom prompt (should use custom + context)
- [ ] Test fallback when enrichment fails (should use basic prompt)

### Acceptance Criteria

✅ Prompts include code conventions from CLAUDE.md
✅ Prompts include relevant file hints based on keywords
✅ Prompts include component structure guidance
✅ Prompts include acceptance criteria
✅ Enrichment gracefully falls back to basic prompt on error

---

## Phase 3: Post-Dispatch Summary (HIGH)
**Effort:** 3-4 hours | **Impact:** 🔥 HIGH - Users know what happened

### Objective
After dispatch completes, show a summary of what was accomplished with actionable next steps.

### Files to Create

#### 1. Backend: Dispatch Summary Endpoint
**File:** `app/python-sidecar/sidecar/api/routes/dispatch.py`

```python
from pydantic import BaseModel

class DispatchSummaryRequest(BaseModel):
    session_id: str
    project_path: str

class FileChange(BaseModel):
    file: str
    lines_added: int
    lines_removed: int
    status: str  # "modified", "added", "deleted"

class DispatchSummaryResponse(BaseModel):
    success: bool
    files_changed: list[FileChange]
    total_added: int
    total_removed: int
    summary_message: str | None
    has_errors: bool

@router.post("/summary")
async def get_dispatch_summary(request: DispatchSummaryRequest):
    """Get summary of what a dispatch accomplished."""
    try:
        from pathlib import Path
        from src.core.git_utils import GitUtils
        from src.agents.dispatcher import get_dispatch_output_path

        project_path = Path(request.project_path)
        git = GitUtils(project_path)

        # Get git changes
        status = git.status()

        files_changed = []
        total_added = 0
        total_removed = 0

        # Get diff stats for each changed file
        for file_status in status.modified + status.added:
            try:
                diff_result = git.run_git_command(["diff", "--numstat", "HEAD", file_status.file])
                if diff_result.success and diff_result.stdout:
                    parts = diff_result.stdout.strip().split('\t')
                    if len(parts) >= 2:
                        added = int(parts[0]) if parts[0] != '-' else 0
                        removed = int(parts[1]) if parts[1] != '-' else 0

                        files_changed.append(FileChange(
                            file=file_status.file,
                            lines_added=added,
                            lines_removed=removed,
                            status=file_status.status
                        ))

                        total_added += added
                        total_removed += removed
            except Exception:
                # If diff fails, just add file without stats
                files_changed.append(FileChange(
                    file=file_status.file,
                    lines_added=0,
                    lines_removed=0,
                    status=file_status.status
                ))

        # Read dispatch output to extract summary
        _, output_file = get_dispatch_output_path(project_path, request.session_id)
        summary_message = None
        has_errors = False

        if output_file.exists():
            output = output_file.read_text(encoding="utf-8", errors="ignore")

            # Look for error indicators
            error_indicators = ["error", "failed", "exception", "traceback"]
            has_errors = any(ind in output.lower() for ind in error_indicators)

            # Try to extract Claude's final message (last non-empty line)
            lines = [l.strip() for l in output.splitlines() if l.strip()]
            if lines:
                summary_message = lines[-1][:200]  # Last line, truncated

        return DispatchSummaryResponse(
            success=not has_errors and len(files_changed) > 0,
            files_changed=files_changed,
            total_added=total_added,
            total_removed=total_removed,
            summary_message=summary_message,
            has_errors=has_errors
        )
    except Exception as e:
        logger.error(f"Failed to generate dispatch summary: {e}")
        return DispatchSummaryResponse(
            success=False,
            files_changed=[],
            total_added=0,
            total_removed=0,
            summary_message=None,
            has_errors=True
        )
```

#### 2. Frontend: Dispatch Summary Component
**File:** `app/src/components/dispatch/DispatchSummary.tsx` (NEW)

```typescript
import { t } from "../../styles/tokens";
import { Button } from "../ui/Button";

interface FileChange {
  file: string;
  lines_added: number;
  lines_removed: number;
  status: string;
}

interface DispatchSummaryProps {
  success: boolean;
  filesChanged: FileChange[];
  totalAdded: number;
  totalRemoved: number;
  summaryMessage: string | null;
  hasErrors: boolean;
  onReviewChanges: () => void;
  onMarkComplete: () => void;
  onCommit: () => void;
  onClose: () => void;
}

export function DispatchSummary({
  success,
  filesChanged,
  totalAdded,
  totalRemoved,
  summaryMessage,
  hasErrors,
  onReviewChanges,
  onMarkComplete,
  onCommit,
  onClose,
}: DispatchSummaryProps) {
  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.7)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 9999,
      }}
      onClick={onClose}
    >
      <div
        style={{
          background: t.surface1,
          borderRadius: 12,
          padding: "24px 28px",
          border: `1px solid ${t.border1}`,
          width: 540,
          maxWidth: "90vw",
          maxHeight: "80vh",
          overflowY: "auto",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16 }}>
          <span style={{ fontSize: 24 }}>
            {success ? "✓" : hasErrors ? "⚠" : "ℹ"}
          </span>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 18, fontWeight: 700, color: t.text0 }}>
              {success ? "Task Completed" : hasErrors ? "Task Completed with Errors" : "Task Ended"}
            </div>
            {summaryMessage && (
              <div style={{ fontSize: 11, color: t.text3, marginTop: 4 }}>
                {summaryMessage}
              </div>
            )}
          </div>
        </div>

        {/* Stats */}
        {filesChanged.length > 0 && (
          <div
            style={{
              display: "flex",
              gap: 20,
              padding: "12px 16px",
              background: t.surface2,
              borderRadius: 8,
              marginBottom: 16,
            }}
          >
            <div>
              <div style={{ fontSize: 10, color: t.text3, textTransform: "uppercase" }}>
                Files Changed
              </div>
              <div style={{ fontSize: 20, fontWeight: 700, color: t.text0 }}>
                {filesChanged.length}
              </div>
            </div>
            <div>
              <div style={{ fontSize: 10, color: t.text3, textTransform: "uppercase" }}>
                Lines Added
              </div>
              <div style={{ fontSize: 20, fontWeight: 700, color: t.green }}>
                +{totalAdded}
              </div>
            </div>
            <div>
              <div style={{ fontSize: 10, color: t.text3, textTransform: "uppercase" }}>
                Lines Removed
              </div>
              <div style={{ fontSize: 20, fontWeight: 700, color: t.red }}>
                -{totalRemoved}
              </div>
            </div>
          </div>
        )}

        {/* File list */}
        {filesChanged.length > 0 && (
          <div
            style={{
              marginBottom: 16,
              maxHeight: 200,
              overflowY: "auto",
              background: t.surface0,
              border: `1px solid ${t.border0}`,
              borderRadius: 8,
              padding: "8px 12px",
            }}
          >
            <div
              style={{
                fontSize: 9,
                color: t.text3,
                textTransform: "uppercase",
                fontWeight: 700,
                marginBottom: 6,
              }}
            >
              Files Changed
            </div>
            {filesChanged.map((file, i) => (
              <div
                key={i}
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  padding: "4px 0",
                  fontSize: 11,
                  fontFamily: "JetBrains Mono, monospace",
                }}
              >
                <span style={{ color: t.text1 }}>{file.file}</span>
                <span style={{ color: t.text3 }}>
                  <span style={{ color: t.green }}>+{file.lines_added}</span>
                  {" "}
                  <span style={{ color: t.red }}>-{file.lines_removed}</span>
                </span>
              </div>
            ))}
          </div>
        )}

        {/* Actions */}
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <div style={{ display: "flex", gap: 8 }}>
            <Button primary onClick={onReviewChanges} style={{ flex: 1 }}>
              Review Changes
            </Button>
            {success && (
              <Button onClick={onMarkComplete} style={{ flex: 1 }}>
                Mark Task Complete
              </Button>
            )}
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <Button onClick={onCommit} style={{ flex: 1 }}>
              Commit Changes
            </Button>
            <Button onClick={onClose} style={{ flex: 1 }}>
              Close
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
```

#### 3. Frontend: Integrate Summary into App Flow
**File:** `app/src/App.tsx`

Add summary state and show after dispatch completes:
```typescript
// Add state
const [showDispatchSummary, setShowDispatchSummary] = useState(false);
const [dispatchSummary, setDispatchSummary] = useState<any>(null);

// After dispatch completes (detect in useEffect watching isDispatching)
useEffect(() => {
  const checkDispatchComplete = async () => {
    if (wasDispatching && !isDispatching && !dispatchFailed) {
      // Dispatch just completed successfully
      if (dispatchJobId && selectedProjectId) {
        try {
          const summary = await api.getDispatchSummary(dispatchJobId, selectedProjectId);
          setDispatchSummary(summary);
          setShowDispatchSummary(true);
        } catch (error) {
          console.error("Failed to get dispatch summary:", error);
        }
      }
    }
  };

  checkDispatchComplete();
}, [isDispatching]);

// Render component
{showDispatchSummary && dispatchSummary && (
  <DispatchSummary
    {...dispatchSummary}
    onReviewChanges={() => {
      setShowDispatchSummary(false);
      // Navigate to Git tab
      setActiveTab("git");
    }}
    onMarkComplete={async () => {
      // Call reconciliation endpoint (Phase 4)
      setShowDispatchSummary(false);
    }}
    onCommit={() => {
      setShowDispatchSummary(false);
      // Open commit dialog
    }}
    onClose={() => setShowDispatchSummary(false)}
  />
)}
```

### Files to Modify

1. `app/python-sidecar/sidecar/api/routes/dispatch.py` - Add summary endpoint
2. `app/src/api/backend.ts` - Add getDispatchSummary method
3. `app/src/App.tsx` - Show summary after dispatch completes

### Testing Checklist

- [ ] Complete a task successfully
- [ ] See summary modal immediately after completion
- [ ] Verify file counts and line stats are accurate
- [ ] Click "Review Changes" → navigates to Git tab
- [ ] Click "Commit Changes" → opens commit dialog
- [ ] Click "Close" → modal disappears
- [ ] Test with task that has errors (should show warning)
- [ ] Test with task that makes no changes (should show info)

### Acceptance Criteria

✅ Summary shows immediately after dispatch completes
✅ File counts and line stats are accurate
✅ Actions work: Review, Mark Complete, Commit, Close
✅ Summary distinguishes success/error/no-changes states

---

## Phase 4: Auto-Reconciliation (MEDIUM)
**Effort:** 3-4 hours | **Impact:** 🎯 MEDIUM - Automated progress tracking

### Objective
Automatically analyze dispatch results and offer to mark tasks complete when changes match expectations.

### Files to Create

#### 1. Core: Reconciliation Agent
**File:** `src/agents/reconciliation_agent.py` (NEW)

```python
"""Reconciliation agent for analyzing dispatch results."""

from dataclasses import dataclass
from pathlib import Path

from ..core.git_utils import GitUtils


@dataclass
class ReconciliationResult:
    """Result of reconciliation analysis."""
    confidence: float  # 0.0-1.0
    recommendation: str  # "mark_complete", "review_needed", "no_action"
    reason: str
    files_analyzed: int


class ReconciliationAgent:
    """Analyzes dispatch results to determine if task is complete."""

    def __init__(self, project_path: Path):
        self.project_path = project_path
        self.git = GitUtils(project_path)

    def analyze_dispatch_result(
        self,
        task_text: str,
        dispatch_output: str,
        session_id: str
    ) -> ReconciliationResult:
        """Analyze if the dispatch accomplished the task.

        Args:
            task_text: Original task description
            dispatch_output: Full output from Claude Code CLI
            session_id: Session ID for this dispatch

        Returns:
            ReconciliationResult with recommendation
        """
        # Get git changes
        status = self.git.status()
        changed_files = status.modified + status.added + status.deleted

        # No changes = no completion
        if not changed_files:
            return ReconciliationResult(
                confidence=0.0,
                recommendation="no_action",
                reason="No files were changed during execution",
                files_analyzed=0
            )

        # Check output for success/error indicators
        output_lower = dispatch_output.lower()

        success_indicators = [
            "task completed",
            "successfully",
            "done",
            "finished",
            "completed successfully"
        ]

        error_indicators = [
            "error:",
            "failed",
            "exception",
            "traceback",
            "could not",
            "unable to"
        ]

        has_success = any(ind in output_lower for ind in success_indicators)
        has_errors = any(err in output_lower for err in error_indicators)

        # Decision logic
        if has_errors:
            return ReconciliationResult(
                confidence=0.2,
                recommendation="review_needed",
                reason=f"Output contains error indicators. {len(changed_files)} files changed but errors detected.",
                files_analyzed=len(changed_files)
            )

        if has_success and len(changed_files) > 0:
            return ReconciliationResult(
                confidence=0.9,
                recommendation="mark_complete",
                reason=f"Task appears complete: {len(changed_files)} files changed and success indicators found.",
                files_analyzed=len(changed_files)
            )

        # Changes made but unclear if complete
        if len(changed_files) > 0:
            return ReconciliationResult(
                confidence=0.6,
                recommendation="review_needed",
                reason=f"{len(changed_files)} files changed but success/completion unclear from output.",
                files_analyzed=len(changed_files)
            )

        return ReconciliationResult(
            confidence=0.0,
            recommendation="no_action",
            reason="Unable to determine task completion status.",
            files_analyzed=0
        )
```

#### 2. Backend: Reconciliation Endpoint
**File:** `app/python-sidecar/sidecar/api/routes/reconciliation.py` (NEW)

```python
"""Reconciliation API routes."""

from fastapi import APIRouter
from pydantic import BaseModel
from pathlib import Path
import logging

router = APIRouter(prefix="/api/reconciliation", tags=["reconciliation"])
logger = logging.getLogger(__name__)


class ReconcileRequest(BaseModel):
    project_path: str
    task_text: str
    session_id: str


class ReconcileResponse(BaseModel):
    confidence: float
    recommendation: str
    reason: str
    files_analyzed: int


@router.post("/analyze")
async def analyze_dispatch(request: ReconcileRequest) -> ReconcileResponse:
    """Analyze dispatch results and recommend next action."""
    try:
        from src.agents.reconciliation_agent import ReconciliationAgent
        from src.agents.dispatcher import get_dispatch_output_path

        project_path = Path(request.project_path)
        agent = ReconciliationAgent(project_path)

        # Read dispatch output
        _, output_file = get_dispatch_output_path(project_path, request.session_id)
        dispatch_output = ""
        if output_file.exists():
            dispatch_output = output_file.read_text(encoding="utf-8", errors="ignore")

        # Analyze
        result = agent.analyze_dispatch_result(
            task_text=request.task_text,
            dispatch_output=dispatch_output,
            session_id=request.session_id
        )

        return ReconcileResponse(
            confidence=result.confidence,
            recommendation=result.recommendation,
            reason=result.reason,
            files_analyzed=result.files_analyzed
        )
    except Exception as e:
        logger.error(f"Reconciliation failed: {e}")
        return ReconcileResponse(
            confidence=0.0,
            recommendation="no_action",
            reason=f"Reconciliation error: {str(e)}",
            files_analyzed=0
        )
```

#### 3. Frontend: Auto-Reconciliation in Summary
**File:** `app/src/components/dispatch/DispatchSummary.tsx`

Add reconciliation banner:
```typescript
interface DispatchSummaryProps {
  // ... existing props
  reconciliation?: {
    confidence: number;
    recommendation: string;
    reason: string;
  };
}

// In component, add banner before actions:
{reconciliation && reconciliation.recommendation === "mark_complete" && (
  <div
    style={{
      background: t.greenMuted,
      border: `1px solid ${t.greenBorder}`,
      borderRadius: 8,
      padding: "12px 14px",
      marginBottom: 16,
    }}
  >
    <div style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
      <span style={{ fontSize: 16 }}>✓</span>
      <div style={{ flex: 1 }}>
        <div style={{ fontSize: 12, fontWeight: 600, color: t.green, marginBottom: 4 }}>
          Recommended: Mark Task Complete
        </div>
        <div style={{ fontSize: 11, color: t.text2 }}>
          {reconciliation.reason}
        </div>
        <div style={{ fontSize: 10, color: t.text3, marginTop: 4 }}>
          Confidence: {Math.round(reconciliation.confidence * 100)}%
        </div>
      </div>
    </div>
  </div>
)}
```

#### 4. Frontend: Call Reconciliation After Dispatch
**File:** `app/src/App.tsx`

Fetch reconciliation when getting summary:
```typescript
const checkDispatchComplete = async () => {
  if (wasDispatching && !isDispatching && !dispatchFailed) {
    if (dispatchJobId && selectedProjectId && lastDispatchContext?.itemRef) {
      try {
        // Get summary
        const summary = await api.getDispatchSummary(dispatchJobId, selectedProjectId);

        // Get reconciliation recommendation
        const reconciliation = await api.reconcileDispatch({
          project_path: selectedProjectId,
          task_text: lastDispatchContext.itemRef.text,
          session_id: dispatchJobId,
        });

        setDispatchSummary({ ...summary, reconciliation });
        setShowDispatchSummary(true);
      } catch (error) {
        console.error("Failed to get dispatch summary:", error);
      }
    }
  }
};
```

### Files to Modify

1. `app/python-sidecar/sidecar/main.py` - Register reconciliation router
2. `app/src/api/backend.ts` - Add reconcileDispatch method
3. `app/src/App.tsx` - Call reconciliation after dispatch
4. `app/src/components/dispatch/DispatchSummary.tsx` - Show recommendation

### Testing Checklist

- [ ] Complete a task successfully
- [ ] See "Recommended: Mark Task Complete" banner with confidence %
- [ ] Verify reason explains why task appears complete
- [ ] Test task that fails → should show "Review Needed"
- [ ] Test task with no changes → should show "No Action"
- [ ] Click "Mark Task Complete" → task checks off in roadmap
- [ ] Verify reconciliation only suggests complete when confidence > 80%

### Acceptance Criteria

✅ Reconciliation runs automatically after dispatch completes
✅ Shows recommendation banner in summary modal
✅ High-confidence (>80%) tasks show "Mark Complete" recommendation
✅ Low-confidence tasks show "Review Needed"
✅ Clicking "Mark Task Complete" updates roadmap

---

## Overall Testing Strategy

### Integration Tests

1. **End-to-End Happy Path**
   - [ ] Select a task from Overview
   - [ ] See enriched prompt in PreFlight modal
   - [ ] Click "Start Session"
   - [ ] See live Claude Code output within 1 second
   - [ ] Watch output update in real-time
   - [ ] Wait for completion
   - [ ] See summary modal with files changed
   - [ ] See reconciliation recommendation
   - [ ] Click "Mark Task Complete"
   - [ ] Verify task is checked in roadmap

2. **Error Path**
   - [ ] Start task that will fail
   - [ ] See live output including error messages
   - [ ] See summary with "Completed with Errors"
   - [ ] See reconciliation recommendation = "Review Needed"
   - [ ] Verify task is NOT auto-checked

3. **No Changes Path**
   - [ ] Start task that makes no file changes
   - [ ] See live output
   - [ ] See summary with "No files changed"
   - [ ] See reconciliation recommendation = "No Action"
   - [ ] Verify task is NOT auto-checked

### Performance Tests

- [ ] Live output polling doesn't cause UI lag
- [ ] Prompt enrichment completes in <500ms
- [ ] Summary generation completes in <300ms
- [ ] Reconciliation completes in <200ms
- [ ] Total dispatch overhead (enrichment + polling + summary) < 1s

### Edge Cases

- [ ] Very long output (>10000 lines) - should truncate/paginate
- [ ] Output file doesn't exist yet - should show "Connecting..."
- [ ] CLAUDE.md doesn't exist - enrichment should fall back gracefully
- [ ] Git repo has no recent changes - should skip recent files section
- [ ] Task text has special characters - keyword extraction should handle
- [ ] Multiple tasks running simultaneously - each should have independent output file

---

## Deployment Checklist

### Phase 1: Live Output
- [ ] Backend endpoint deployed
- [ ] Frontend hook tested
- [ ] Fake messages removed
- [ ] Verified on real task execution
- [ ] **SHIP IT** 🚀

### Phase 2: Enriched Prompts
- [ ] PromptEnricher tested with multiple task types
- [ ] Endpoint deployed
- [ ] Frontend integration tested
- [ ] Fallback behavior verified
- [ ] **SHIP IT** 🚀

### Phase 3: Post-Dispatch Summary
- [ ] Summary endpoint tested with git operations
- [ ] Component tested with various scenarios
- [ ] Actions wired up correctly
- [ ] **SHIP IT** 🚀

### Phase 4: Reconciliation
- [ ] ReconciliationAgent tested with various outputs
- [ ] Confidence scores calibrated
- [ ] Auto-mark behavior tested
- [ ] **SHIP IT** 🚀

---

## Success Metrics

After implementing all phases:

1. **Time to First Output:** <1 second (currently 26+ seconds)
2. **Task Success Rate:** >80% (enriched prompts improve context)
3. **User Confidence:** Users see what happened, can take action
4. **Auto-Completion Rate:** ~60% of successful tasks auto-marked complete
5. **User Satisfaction:** No more "what just happened?" confusion

---

## Rollback Plan

Each phase is independent and can be rolled back:

- **Phase 1:** Revert DispatchOverlay changes, remove endpoint
- **Phase 2:** Remove enrichment call from OverviewTab, remove endpoint
- **Phase 3:** Remove summary modal, remove endpoint
- **Phase 4:** Remove reconciliation call, remove endpoint

All phases are additive - no breaking changes to existing code.
