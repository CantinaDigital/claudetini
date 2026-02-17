import { useCallback, useEffect, useRef, useState } from "react";
import { t } from "../../styles/tokens";
import { Section } from "../ui/Section";
import { StatusDot } from "../ui/StatusDot";
import { Button } from "../ui/Button";
import { Toggle } from "../ui/Toggle";
import { Tag } from "../ui/Tag";
import { Icons } from "../ui/Icons";
import { Select } from "../ui/Select";
import { useSettingsStore } from "../../stores/settingsStore";
import { api, isBackendConnected } from "../../api/backend";
import { toast } from "../ui/Toast";
import type { ProviderInfo, BranchStrategyInfo, ContextFileInfo, BudgetInfo } from "../../types";

interface SettingsTabProps {
  projectPath?: string | null;
  isActive?: boolean;
  backendConnected: boolean;
  onShowConfirm?: (config: {
    title: string;
    message: string;
    confirmLabel: string;
    danger?: boolean;
    onConfirm: () => void;
  } | null) => void;
}

// Static descriptions for preflight checks (store only persists name → boolean)
const PREFLIGHT_DESCRIPTIONS: Record<string, { d: string; locked: boolean }> = {
  "Uncommitted changes": { d: "Warn if working tree dirty", locked: false },
  "Branch behind remote": { d: "Check origin freshness", locked: false },
  "Stale dependencies": { d: "Check lockfile freshness", locked: false },
  "Previous session incomplete": { d: "Warn on non-zero exit", locked: false },
  "Editor conflict detection": { d: "Files modified < 30s ago", locked: false },
  "Disk space (Blitz)": { d: "Block if < 2GB per worktree", locked: true },
};

// Static descriptions for scheduling toggles
const SCHEDULING_DESCRIPTIONS: Record<string, string> = {
  "Do-Not-Disturb mode": "Pause all dispatches and queue",
  "Active editor detection": "Detect VS Code / Cursor writing to project files",
  "Auto-resume queue": "Dispatch queued items when DND lifts",
  "Conflict prevention": "Block dispatch if files modified < 30s ago",
};

// Tasks that cannot have their provider changed
const LOCKED_TASKS = new Set(["Security Review", "Quality Gates"]);

// Fallback data when backend is unavailable
const FALLBACK_PROVIDERS: ProviderInfo[] = [
  { name: "Claude Code", version: "unknown", status: "not configured", color: "#8b7cf6", installed: false },
  { name: "Codex CLI", version: "unknown", status: "not configured", color: "#34d399", installed: false },
  { name: "Gemini CLI", version: "unknown", status: "not configured", color: "#60a5fa", installed: false },
];

const FALLBACK_BUDGET: BudgetInfo = { monthly: 0, spent: 0, weeklySpent: 0, perSession: 0 };

export function SettingsTab({ projectPath, isActive = true, backendConnected, onShowConfirm }: SettingsTabProps) {
  // --- Settings store (persisted) ---
  const lightModel = useSettingsStore((s) => s.lightModel);
  const setLightModel = useSettingsStore((s) => s.setLightModel);
  const preSessionHooks = useSettingsStore((s) => s.preSessionHooks);
  const addPreSessionHook = useSettingsStore((s) => s.addPreSessionHook);
  const removePreSessionHook = useSettingsStore((s) => s.removePreSessionHook);
  const autoDispatchEnabled = useSettingsStore((s) => s.autoDispatchEnabled);
  const setAutoDispatch = useSettingsStore((s) => s.setAutoDispatch);

  // Task routing (persisted)
  const taskRouting = useSettingsStore((s) => s.taskRouting);
  const setTaskRouting = useSettingsStore((s) => s.setTaskRouting);

  // Preflight checks (persisted)
  const preflightChecks = useSettingsStore((s) => s.preflightChecks);
  const setPreflightCheck = useSettingsStore((s) => s.setPreflightCheck);

  // Scheduling toggles (persisted)
  const schedulingToggles = useSettingsStore((s) => s.schedulingToggles);
  const setSchedulingToggle = useSettingsStore((s) => s.setSchedulingToggle);

  // Branch strategy toggles (persisted)
  const branchStrategyToggles = useSettingsStore((s) => s.branchStrategyToggles);
  const setBranchStrategyToggle = useSettingsStore((s) => s.setBranchStrategyToggle);

  // Hook groups (persisted)
  const postSessionHooks = useSettingsStore((s) => s.postSessionHooks);
  const preMergeHooks = useSettingsStore((s) => s.preMergeHooks);
  const postMergeHooks = useSettingsStore((s) => s.postMergeHooks);
  const addHookToGroup = useSettingsStore((s) => s.addHookToGroup);
  const toggleHookInGroup = useSettingsStore((s) => s.toggleHookInGroup);
  const removeHookFromGroup = useSettingsStore((s) => s.removeHookFromGroup);

  // --- API-fetched state ---
  const [providers, setProviders] = useState<ProviderInfo[]>(FALLBACK_PROVIDERS);
  const [branchStrategy, setBranchStrategy] = useState<BranchStrategyInfo | null>(null);
  const [budget, setBudget] = useState<BudgetInfo>(FALLBACK_BUDGET);
  const [contextFiles, setContextFiles] = useState<ContextFileInfo[]>([]);

  // --- UI state ---
  const [addingHook, setAddingHook] = useState<string | null>(null);
  const [addHookText, setAddHookText] = useState("");
  const [testingProvider, setTestingProvider] = useState<string | null>(null);
  const [generatingFile, setGeneratingFile] = useState<string | null>(null);
  const hasLoaded = useRef(false);

  const budgetPct = budget.monthly > 0 ? Math.round((budget.spent / budget.monthly) * 100) : 0;

  // --- Fetch API data on mount/project change ---
  // These settings endpoints may not exist in the backend yet.
  // Use .catch() to fast-fail with defaults instead of blocking on timeout.
  const fetchSettings = useCallback(async () => {
    if (!projectPath || !isBackendConnected()) return;

    const _t0 = performance.now();
    const results = await Promise.allSettled([
      api.detectProviders(projectPath).catch(() => FALLBACK_PROVIDERS),
      api.getBranchStrategy(projectPath).catch(() => null),
      api.getBudget(projectPath).catch(() => FALLBACK_BUDGET),
      api.getContextFiles(projectPath).catch(() => [] as ContextFileInfo[]),
    ]);

    if (results[0].status === "fulfilled") setProviders(results[0].value);
    if (results[1].status === "fulfilled" && results[1].value) setBranchStrategy(results[1].value);
    if (results[2].status === "fulfilled") setBudget(results[2].value);
    if (results[3].status === "fulfilled") setContextFiles(results[3].value);
    console.log(`%c[SettingsTab] loaded in ${Math.round(performance.now() - _t0)}ms`, "color: #34d399");
  }, [projectPath]);

  // Reset hasLoaded on project change
  useEffect(() => { hasLoaded.current = false; }, [projectPath]);

  useEffect(() => {
    if (!isActive && !hasLoaded.current) return;
    hasLoaded.current = true;
    void fetchSettings();
  }, [fetchSettings, isActive]);

  // --- Hook management ---
  const handleAddHookToGroup = (group: string) => {
    setAddingHook(group);
    setAddHookText("");
  };

  const handleConfirmAddHook = (group: string) => {
    if (!addHookText.trim()) {
      setAddingHook(null);
      return;
    }
    if (group === "preSession") {
      addPreSessionHook(addHookText.trim());
    } else {
      addHookToGroup(group as "postSessionHooks" | "preMergeHooks" | "postMergeHooks", addHookText.trim());
    }
    setAddingHook(null);
    setAddHookText("");
  };

  const handleToggleHook = (group: string, index: number) => {
    if (group === "preSession") {
      toggleHookInGroup("preSessionHooks", index);
    } else {
      toggleHookInGroup(group as "postSessionHooks" | "preMergeHooks" | "postMergeHooks", index);
    }
  };

  const handleRemoveHook = (group: string, index: number) => {
    if (group === "preSession") {
      removePreSessionHook(index);
    } else {
      removeHookFromGroup(group as "postSessionHooks" | "preMergeHooks" | "postMergeHooks", index);
    }
  };

  // --- Provider test ---
  const handleProviderTest = async (providerName: string) => {
    setTestingProvider(providerName);
    try {
      const result = await api.testProvider(providerName);
      if (result.success) {
        toast.success("Provider OK", result.message);
        // Refresh providers to get updated status
        void fetchSettings();
      } else {
        toast.error("Provider Error", result.message);
      }
    } catch (e) {
      toast.error("Test Failed", e instanceof Error ? e.message : `Failed to test ${providerName}`);
    } finally {
      setTestingProvider(null);
    }
  };

  // --- Danger zone handlers ---
  const handleResetGates = () => {
    if (!onShowConfirm || !projectPath) return;
    onShowConfirm({
      title: "Reset Gates",
      message: "This will clear all quality gate results and trends. This cannot be undone.",
      confirmLabel: "Reset",
      danger: true,
      onConfirm: async () => {
        try {
          const result = await api.resetGates(projectPath);
          if (result.success) {
            toast.success("Gates Reset", result.message);
          } else {
            toast.error("Reset Failed", result.message);
          }
        } catch (e) {
          toast.error("Reset Failed", e instanceof Error ? e.message : "Failed to reset gates");
        }
      },
    });
  };

  const handleClearHistory = () => {
    if (!onShowConfirm || !projectPath) return;
    onShowConfirm({
      title: "Clear History",
      message: "This will remove all session, commit, and log history. This cannot be undone.",
      confirmLabel: "Clear",
      danger: true,
      onConfirm: async () => {
        try {
          const result = await api.clearHistory(projectPath);
          if (result.success) {
            toast.success("History Cleared", result.message);
          } else {
            toast.error("Clear Failed", result.message);
          }
        } catch (e) {
          toast.error("Clear Failed", e instanceof Error ? e.message : "Failed to clear history");
        }
      },
    });
  };

  const handleRemoveProject = () => {
    if (!onShowConfirm || !projectPath) return;
    onShowConfirm({
      title: "Remove Project",
      message: "This will permanently delete all project data from Claudetini. Your source code will NOT be affected. This cannot be undone.",
      confirmLabel: "Remove",
      danger: true,
      onConfirm: async () => {
        try {
          const result = await api.removeProject(projectPath);
          if (result.success) {
            toast.success("Project Removed", result.message);
          } else {
            toast.error("Remove Failed", result.message);
          }
        } catch (e) {
          toast.error("Remove Failed", e instanceof Error ? e.message : "Failed to remove project");
        }
      },
    });
  };

  // --- Context file management ---
  const handleContextFileAction = async (file: string, action: string) => {
    if (!projectPath) return;
    setGeneratingFile(file);
    try {
      const result = await api.generateContextFile(projectPath, file);
      if (result.success) {
        toast.success(action, result.message);
        // Refresh context files list
        try {
          const updated = await api.getContextFiles(projectPath);
          setContextFiles(updated);
        } catch { /* keep existing list */ }
      } else {
        toast.error(`${action} Failed`, result.message);
      }
    } catch (e) {
      toast.error(`${action} Failed`, e instanceof Error ? e.message : `Failed to ${action.toLowerCase()} ${file}`);
    } finally {
      setGeneratingFile(null);
    }
  };

  // --- Routing helpers ---
  const routingEntries = Object.entries(taskRouting);

  return (
    <div className="w-full flex flex-col gap-[18px] animate-fade-in">

      {/* 1. Provider Registry */}
      <Section label="Available Providers">
        <div className="py-1.5">
          {providers.map((p, i) => (
            <div
              key={p.name}
              className={`flex items-center gap-3 px-4 py-2.5 ${
                i < providers.length - 1 ? "border-b border-mc-border-0" : ""
              }`}
            >
              <div
                className="w-2.5 h-2.5 rounded-full shrink-0"
                style={{ background: p.color, boxShadow: `0 0 8px ${p.color}40` }}
              />
              <span className="text-[13px] font-semibold text-mc-text-0 min-w-[120px]">{p.name}</span>
              <span className="text-[11px] font-mono text-mc-text-3">{p.version}</span>
              <div className="flex-1" />
              <Tag
                color={p.status === "authenticated" ? t.green : p.status === "error" ? t.red : t.amber}
                bg={p.status === "authenticated" ? t.greenMuted : p.status === "error" ? t.redMuted : t.amberMuted}
              >
                {p.status === "authenticated" ? "\u2713 Auth" : p.status === "error" ? "\u2717 Error" : "\u26A0 Setup"}
              </Tag>
              <Button
                small
                onClick={() => handleProviderTest(p.name)}
                disabled={testingProvider === p.name}
              >
                {testingProvider === p.name ? "Testing..." : p.status === "authenticated" ? "Test" : "Setup"}
              </Button>
            </div>
          ))}
        </div>
      </Section>

      {/* 2. Task Routing */}
      <Section label="Task Type \u2192 Provider Routing">
        <div className="py-1">
          <div className="flex px-4 py-1.5 border-b border-mc-border-0">
            <span className="mc-label flex-1">Task</span>
            <span className="mc-label w-[150px]">Provider</span>
            <span className="w-9" />
          </div>
          {routingEntries.map(([task, provider], i) => {
            const locked = LOCKED_TASKS.has(task);
            return (
              <div
                key={task}
                className={`flex items-center gap-3 px-4 py-2 ${
                  i < routingEntries.length - 1 ? "border-b border-mc-border-0" : ""
                }`}
              >
                <span className="text-[12.5px] font-medium text-mc-text-1 flex-1">{task}</span>
                <Select
                  disabled={locked}
                  value={provider}
                  onChange={(val) => setTaskRouting(task, val)}
                  small
                  options={[
                    { value: "Claude", label: "Claude" },
                    { value: "Codex", label: "Codex" },
                    { value: "Gemini", label: "Gemini" },
                  ]}
                  className="min-w-[120px]"
                />
                {locked ? (
                  <span className="w-9 flex justify-center text-mc-text-3">
                    <Icons.lock size={12} />
                  </span>
                ) : (
                  <span className="w-9" />
                )}
              </div>
            );
          })}
        </div>
      </Section>

      {/* 3. Branch Strategy */}
      <Section label="Branch Strategy">
        <div className="px-4 py-3.5">
          <div className="flex items-center gap-3 mb-3">
            <Tag color={t.cyan} bg={t.cyanMuted}>
              Detected: {branchStrategy?.detected || "Unknown"}
            </Tag>
            <span className="text-[11px] text-mc-text-3">
              {branchStrategy?.evidence || "No branch strategy data available"}
            </span>
          </div>
          {([
            { key: "autoCreateBranches" as const, name: "Auto-create feature branches", desc: "Creates feature/cp-<slug> before dispatch" },
            { key: "autoPR" as const, name: "Auto-PR on completion", desc: "gh pr create when item completed" },
            { key: "autoMerge" as const, name: "Auto-merge after gates pass", desc: "Merge PR when all gates pass" },
          ]).map((s) => (
            <div
              key={s.key}
              className="flex items-center gap-3 px-3 py-2 rounded-lg bg-mc-surface-2 mb-1"
            >
              <div className="flex-1">
                <div className="text-xs font-medium text-mc-text-1">{s.name}</div>
                <div className="text-[10.5px] text-mc-text-3 mt-px">{s.desc}</div>
              </div>
              <Toggle
                on={branchStrategyToggles[s.key]}
                onClick={() => setBranchStrategyToggle(s.key, !branchStrategyToggles[s.key])}
              />
            </div>
          ))}
        </div>
      </Section>

      {/* 4. Token Budget */}
      <Section label="Token Budget">
        <div className="px-4 py-3.5">
          <div className="grid grid-cols-4 gap-2.5 mb-3.5">
            {[
              { l: "Monthly", v: `$${budget.monthly.toFixed(2)}`, s: "Soft limit" },
              { l: "Month Spent", v: `$${budget.spent.toFixed(2)}`, s: `${budgetPct}%` },
              { l: "Week Spent", v: `$${budget.weeklySpent.toFixed(2)}`, s: "All costs" },
              { l: "Per-Session", v: `$${budget.perSession.toFixed(2)}`, s: "Hard stop" },
            ].map((stat) => (
              <div
                key={stat.l}
                className="px-3 py-2.5 rounded-lg bg-mc-surface-2 border border-mc-border-0"
              >
                <div className="mc-label tracking-[0.06em] mb-1">
                  {stat.l}
                </div>
                <div className="text-base font-bold font-mono text-mc-text-0 mb-0.5">
                  {stat.v}
                </div>
                <div className="text-[10px] text-mc-text-3">{stat.s}</div>
              </div>
            ))}
          </div>
          <div className="flex items-center gap-2.5">
            <div className="flex-1 h-1.5 bg-mc-surface-3 rounded-sm overflow-hidden relative">
              <div
                className="h-full rounded-sm"
                style={{
                  width: `${budgetPct}%`,
                  background: `linear-gradient(90deg, ${t.accent}, ${t.accentDark})`,
                }}
              />
              <div className="absolute top-[-2px] w-px h-2.5 bg-mc-text-3 opacity-40" style={{ left: "80%" }} />
            </div>
            <span className="text-[11px] font-mono text-mc-text-3">{budgetPct}%</span>
          </div>
        </div>
      </Section>

      {/* 5. Light Model */}
      <Section label="Light Model (for small tasks)">
        <div className="px-4 py-3.5">
          <div className="text-[11px] text-mc-text-3 mb-2.5">
            Used for commit message generation and other lightweight tasks. Saves your high-end model tokens for real coding work.
          </div>
          <Select
            value={lightModel}
            onChange={setLightModel}
            options={[
              { value: "claude-haiku-4-5-20251001", label: "Claude Haiku 4.5 (Recommended)" },
              { value: "claude-sonnet-4-5-20250929", label: "Claude Sonnet 4.5" },
              { value: "claude-opus-4-6", label: "Claude Opus 4.6" },
            ]}
            className="min-w-[260px]"
          />
        </div>
      </Section>

      {/* 6. Pre-Flight Checks */}
      <Section label="Pre-Flight Checks">
        <div className="py-1">
          {Object.entries(preflightChecks).map(([name, enabled]) => {
            const meta = PREFLIGHT_DESCRIPTIONS[name];
            const locked = meta?.locked ?? false;
            return (
              <div
                key={name}
                className="flex items-center gap-3 px-4 py-[9px] border-b border-mc-border-0"
              >
                <div className="flex-1">
                  <div className="text-[12.5px] font-medium text-mc-text-1">{name}</div>
                  <div className="text-[10.5px] text-mc-text-3 mt-px">
                    {meta?.d || "Toggle this check"}
                  </div>
                </div>
                {locked && <Tag color={t.text3}>Required</Tag>}
                <Toggle
                  on={enabled}
                  locked={locked}
                  onClick={() => !locked && setPreflightCheck(name, !enabled)}
                />
              </div>
            );
          })}
        </div>
      </Section>

      {/* 6. Smart Scheduling */}
      <Section label="Smart Scheduling">
        <div className="py-1">
          {/* Auto-dispatch queue toggle (persisted) */}
          <div className="flex items-center gap-3 px-4 py-[9px] border-b border-mc-border-0">
            <div className="flex-1">
              <div className="text-[12.5px] font-medium text-mc-text-1">Auto-dispatch queue on session end</div>
              <div className="text-[10.5px] text-mc-text-3 mt-px">Automatically start the next queued task when a session finishes</div>
            </div>
            <Toggle
              on={autoDispatchEnabled}
              onClick={() => setAutoDispatch(!autoDispatchEnabled)}
            />
          </div>
          {Object.entries(schedulingToggles).map(([name, enabled]) => (
            <div
              key={name}
              className="flex items-center gap-3 px-4 py-[9px] border-b border-mc-border-0"
            >
              <div className="flex-1">
                <div className="text-[12.5px] font-medium text-mc-text-1">{name}</div>
                <div className="text-[10.5px] text-mc-text-3 mt-px">
                  {SCHEDULING_DESCRIPTIONS[name] || "Toggle this setting"}
                </div>
              </div>
              <Toggle
                on={enabled}
                onClick={() => setSchedulingToggle(name, !enabled)}
              />
            </div>
          ))}
        </div>
      </Section>

      {/* 7. Session Hooks */}
      <Section label="Session Hooks">
        <div className="px-4 py-2.5">
          {[
            { label: "Pre-Session", key: "preSession", hooks: preSessionHooks, desc: "Run before dispatching Claude Code" },
            { label: "Post-Session", key: "postSessionHooks", hooks: postSessionHooks, desc: "Run after session completes" },
            { label: "Pre-Merge (Blitz)", key: "preMergeHooks", hooks: preMergeHooks, desc: "Run before merging blitz branches" },
            { label: "Post-Merge (Blitz)", key: "postMergeHooks", hooks: postMergeHooks, desc: "Run after blitz merge" },
          ].map((group, gi) => (
            <div key={group.key} className={gi < 3 ? "mb-3.5" : ""}>
              <div className="flex items-center gap-2 mb-1.5">
                <span className="mc-label tracking-[0.06em]">
                  {group.label}
                </span>
                <span className="text-[10px] text-mc-text-3">{group.desc}</span>
              </div>
              {group.hooks.map((h, hi) => (
                <div
                  key={`${h.cmd}-${hi}`}
                  className="flex items-center gap-2.5 px-2.5 py-1.5 rounded-md bg-mc-surface-2 mb-1 border border-mc-border-0"
                >
                  <code className="text-[11px] font-mono text-mc-text-1 flex-1">{h.cmd}</code>
                  <Toggle
                    on={h.enabled}
                    onClick={() => handleToggleHook(group.key, hi)}
                  />
                  <button
                    onClick={() => handleRemoveHook(group.key, hi)}
                    className="text-[9px] text-mc-text-3 bg-transparent border-none cursor-pointer px-1 py-0.5"
                    title="Remove hook"
                  >
                    {"\u00D7"}
                  </button>
                </div>
              ))}
              {addingHook === group.key ? (
                <div className="flex gap-1.5 mt-1">
                  <input
                    autoFocus
                    value={addHookText}
                    onChange={(e) => setAddHookText(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") handleConfirmAddHook(group.key);
                      if (e.key === "Escape") setAddingHook(null);
                    }}
                    placeholder="Command to run..."
                    className="flex-1 text-[11px] font-mono text-mc-text-1 bg-mc-surface-2 border border-mc-accent-border rounded-md px-2.5 py-[5px] outline-none"
                  />
                  <Button small onClick={() => handleConfirmAddHook(group.key)}>Add</Button>
                  <Button small onClick={() => setAddingHook(null)}>Cancel</Button>
                </div>
              ) : (
                <Button small className="mt-1" onClick={() => handleAddHookToGroup(group.key)}>
                  + Add Hook
                </Button>
              )}
            </div>
          ))}
        </div>
      </Section>

      {/* 8. Context File Management */}
      <Section label="Context File Management">
        <div className="py-1">
          {contextFiles.length === 0 ? (
            <div className="px-4 py-3 text-[11px] text-mc-text-3 italic">
              {backendConnected ? "No context files detected" : "Connect to backend to detect context files"}
            </div>
          ) : (
            contextFiles.map((f, i) => (
              <div
                key={f.file}
                className={`flex items-center gap-2.5 px-4 py-[9px] ${
                  i < contextFiles.length - 1 ? "border-b border-mc-border-0" : ""
                }`}
              >
                <span className="text-sm shrink-0">{f.icon}</span>
                <span className="text-xs font-semibold font-mono text-mc-text-0 min-w-[140px] shrink-0">
                  {f.file}
                </span>
                <StatusDot status={f.status === "missing" ? "warn" : f.status} size={5} />
                <span className="text-[11px] text-mc-text-3 flex-1">{f.detail}</span>
                <Button
                  small
                  onClick={() => handleContextFileAction(f.file, f.status === "pass" ? "Regenerate" : "Generate")}
                  disabled={generatingFile === f.file}
                >
                  {generatingFile === f.file ? "..." : f.status === "pass" ? "Regenerate" : "Generate"}
                </Button>
              </div>
            ))
          )}
        </div>
      </Section>

      {/* 9. Danger Zone */}
      <div className="px-4 py-3.5 rounded-[10px] bg-mc-red-muted border border-mc-red-border">
        <div className="mc-label text-mc-red tracking-[0.08em] mb-2.5">
          Danger Zone
        </div>
        <div className="flex gap-2.5">
          <Button small danger onClick={handleResetGates}>
            Reset Gates
          </Button>
          <Button small danger onClick={handleClearHistory}>
            Clear History
          </Button>
          <Button small danger onClick={handleRemoveProject}>
            Remove Project
          </Button>
        </div>
      </div>
    </div>
  );
}
