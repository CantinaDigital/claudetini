import { create } from "zustand";

export type FallbackProvider = "codex" | "gemini";
export type UsageMode = "subscription" | "api";

const SETTINGS_STORAGE_KEY = "claudetini.fallback.settings.v1";

export interface HookCommand {
  cmd: string;
  enabled: boolean;
}

interface StoredSettings {
  codexPath: string;
  geminiPath: string;
  preferredFallback: FallbackProvider;
  usageMode: UsageMode;
  claudeRemainingPct: number;
  fallbackThresholdPct: number;
  preSessionHooks: HookCommand[];
  reconciliationEnabled: boolean;
  reconciliationConfidenceThreshold: number;
  autoDispatchEnabled: boolean;
  // Model used for lightweight tasks (commit messages, summaries, etc.)
  lightModel: string;
  // Task routing (issue #9)
  taskRouting: Record<string, string>;
  // Pre-flight check toggles (issue #10)
  preflightChecks: Record<string, boolean>;
  // Scheduling toggles (issue #11)
  schedulingToggles: Record<string, boolean>;
  // Branch strategy toggles (issue #12)
  branchStrategyToggles: {
    autoCreateBranches: boolean;
    autoPR: boolean;
    autoMerge: boolean;
  };
  // Post-session / merge hooks (issue #13)
  postSessionHooks: HookCommand[];
  preMergeHooks: HookCommand[];
  postMergeHooks: HookCommand[];
  // Pre-push hook toggle (issue #14)
  prePushHookEnabled: boolean;
  // Max parallel agents for parallel execution
  maxParallelAgents: number;
}

interface SettingsStore extends StoredSettings {
  setLightModel: (model: string) => void;
  setPreferredFallback: (provider: FallbackProvider) => void;
  addPreSessionHook: (cmd: string) => void;
  updatePreSessionHook: (index: number, patch: Partial<HookCommand>) => void;
  removePreSessionHook: (index: number) => void;
  setAutoDispatch: (enabled: boolean) => void;
  setTaskRouting: (task: string, provider: string) => void;
  setPreflightCheck: (name: string, enabled: boolean) => void;
  setSchedulingToggle: (name: string, enabled: boolean) => void;
  setBranchStrategyToggle: (key: keyof StoredSettings["branchStrategyToggles"], value: boolean) => void;
  addHookToGroup: (group: "postSessionHooks" | "preMergeHooks" | "postMergeHooks", cmd: string) => void;
  toggleHookInGroup: (group: "preSessionHooks" | "postSessionHooks" | "preMergeHooks" | "postMergeHooks", index: number) => void;
  removeHookFromGroup: (group: "preSessionHooks" | "postSessionHooks" | "preMergeHooks" | "postMergeHooks", index: number) => void;
  setPrePushHookEnabled: (enabled: boolean) => void;
  setMaxParallelAgents: (count: number) => void;
}

const DEFAULT_TASK_ROUTING: Record<string, string> = {
  Coding: "Claude",
  Tests: "Claude",
  Documentation: "Gemini",
  Refactoring: "Claude",
  "CI/CD": "Codex",
  "Security Review": "Claude",
  "Quality Gates": "Claude",
};

const DEFAULT_PREFLIGHT_CHECKS: Record<string, boolean> = {
  "Uncommitted changes": true,
  "Branch behind remote": true,
  "Stale dependencies": false,
  "Previous session incomplete": true,
  "Editor conflict detection": false,
  "Disk space (Blitz)": true,
};

const DEFAULT_SCHEDULING_TOGGLES: Record<string, boolean> = {
  "Do-Not-Disturb mode": false,
  "Active editor detection": false,
  "Auto-resume queue": true,
  "Conflict prevention": false,
};

const DEFAULT_SETTINGS: StoredSettings = {
  codexPath: "codex",
  geminiPath: "gemini",
  preferredFallback: "codex",
  usageMode: "subscription",
  claudeRemainingPct: 100,
  fallbackThresholdPct: 10,
  preSessionHooks: [],
  reconciliationEnabled: true,
  reconciliationConfidenceThreshold: 50,
  autoDispatchEnabled: false,
  lightModel: "claude-haiku-4-5-20251001",
  taskRouting: DEFAULT_TASK_ROUTING,
  preflightChecks: DEFAULT_PREFLIGHT_CHECKS,
  schedulingToggles: DEFAULT_SCHEDULING_TOGGLES,
  branchStrategyToggles: {
    autoCreateBranches: false,
    autoPR: false,
    autoMerge: false,
  },
  postSessionHooks: [],
  preMergeHooks: [],
  postMergeHooks: [],
  prePushHookEnabled: false,
  maxParallelAgents: 3,
};

/** Extract storable fields from state (strips action functions). */
function toStorable(state: SettingsStore): StoredSettings {
  return {
    codexPath: state.codexPath,
    geminiPath: state.geminiPath,
    preferredFallback: state.preferredFallback,
    usageMode: state.usageMode,
    claudeRemainingPct: state.claudeRemainingPct,
    fallbackThresholdPct: state.fallbackThresholdPct,
    preSessionHooks: state.preSessionHooks,
    reconciliationEnabled: state.reconciliationEnabled,
    reconciliationConfidenceThreshold: state.reconciliationConfidenceThreshold,
    autoDispatchEnabled: state.autoDispatchEnabled,
    lightModel: state.lightModel,
    taskRouting: state.taskRouting,
    preflightChecks: state.preflightChecks,
    schedulingToggles: state.schedulingToggles,
    branchStrategyToggles: state.branchStrategyToggles,
    postSessionHooks: state.postSessionHooks,
    preMergeHooks: state.preMergeHooks,
    postMergeHooks: state.postMergeHooks,
    prePushHookEnabled: state.prePushHookEnabled,
    maxParallelAgents: state.maxParallelAgents,
  };
}

function _parseHookArray(raw: unknown): HookCommand[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .filter(
      (hook): hook is HookCommand =>
        Boolean(hook) &&
        typeof hook === "object" &&
        typeof (hook as HookCommand).cmd === "string"
    )
    .map((hook) => ({ cmd: hook.cmd.trim(), enabled: Boolean(hook.enabled) }))
    .filter((hook) => hook.cmd.length > 0);
}

function loadSettings(): StoredSettings {
  if (typeof window === "undefined") return DEFAULT_SETTINGS;
  try {
    const raw = window.localStorage.getItem(SETTINGS_STORAGE_KEY);
    if (!raw) return DEFAULT_SETTINGS;
    const parsed = JSON.parse(raw) as Partial<StoredSettings>;
    return {
      codexPath:
        typeof parsed.codexPath === "string" && parsed.codexPath.trim()
          ? parsed.codexPath
          : DEFAULT_SETTINGS.codexPath,
      geminiPath:
        typeof parsed.geminiPath === "string" && parsed.geminiPath.trim()
          ? parsed.geminiPath
          : DEFAULT_SETTINGS.geminiPath,
      preferredFallback:
        parsed.preferredFallback === "gemini" ? "gemini" : DEFAULT_SETTINGS.preferredFallback,
      usageMode: parsed.usageMode === "api" ? "api" : DEFAULT_SETTINGS.usageMode,
      claudeRemainingPct: _clampPct(parsed.claudeRemainingPct, DEFAULT_SETTINGS.claudeRemainingPct),
      fallbackThresholdPct: _clampPct(
        parsed.fallbackThresholdPct,
        DEFAULT_SETTINGS.fallbackThresholdPct
      ),
      preSessionHooks: _parseHookArray(parsed.preSessionHooks),
      reconciliationEnabled:
        typeof parsed.reconciliationEnabled === "boolean"
          ? parsed.reconciliationEnabled
          : DEFAULT_SETTINGS.reconciliationEnabled,
      reconciliationConfidenceThreshold: _clampRange(
        parsed.reconciliationConfidenceThreshold,
        30,
        90,
        DEFAULT_SETTINGS.reconciliationConfidenceThreshold
      ),
      autoDispatchEnabled:
        typeof parsed.autoDispatchEnabled === "boolean"
          ? parsed.autoDispatchEnabled
          : DEFAULT_SETTINGS.autoDispatchEnabled,
      lightModel:
        typeof parsed.lightModel === "string" && parsed.lightModel.trim()
          ? parsed.lightModel
          : DEFAULT_SETTINGS.lightModel,
      taskRouting:
        parsed.taskRouting && typeof parsed.taskRouting === "object"
          ? { ...DEFAULT_TASK_ROUTING, ...parsed.taskRouting }
          : DEFAULT_SETTINGS.taskRouting,
      preflightChecks:
        parsed.preflightChecks && typeof parsed.preflightChecks === "object"
          ? { ...DEFAULT_PREFLIGHT_CHECKS, ...parsed.preflightChecks }
          : DEFAULT_SETTINGS.preflightChecks,
      schedulingToggles:
        parsed.schedulingToggles && typeof parsed.schedulingToggles === "object"
          ? { ...DEFAULT_SCHEDULING_TOGGLES, ...parsed.schedulingToggles }
          : DEFAULT_SETTINGS.schedulingToggles,
      branchStrategyToggles:
        parsed.branchStrategyToggles && typeof parsed.branchStrategyToggles === "object"
          ? { ...DEFAULT_SETTINGS.branchStrategyToggles, ...parsed.branchStrategyToggles }
          : DEFAULT_SETTINGS.branchStrategyToggles,
      postSessionHooks: _parseHookArray(parsed.postSessionHooks),
      preMergeHooks: _parseHookArray(parsed.preMergeHooks),
      postMergeHooks: _parseHookArray(parsed.postMergeHooks),
      prePushHookEnabled:
        typeof parsed.prePushHookEnabled === "boolean"
          ? parsed.prePushHookEnabled
          : DEFAULT_SETTINGS.prePushHookEnabled,
      maxParallelAgents: _clampRange(
        parsed.maxParallelAgents,
        1,
        8,
        DEFAULT_SETTINGS.maxParallelAgents
      ),
    };
  } catch {
    return DEFAULT_SETTINGS;
  }
}

function persistSettings(settings: StoredSettings): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(SETTINGS_STORAGE_KEY, JSON.stringify(settings));
  } catch {
    // No-op if storage is unavailable.
  }
}

/** Helper: update a field and persist. */
function updateAndPersist(
  set: (fn: (state: SettingsStore) => Partial<SettingsStore>) => void,
  patch: Partial<StoredSettings>
) {
  set((state) => {
    const next = toStorable({ ...state, ...patch } as SettingsStore);
    persistSettings(next);
    return patch;
  });
}

const initial = loadSettings();

export const useSettingsStore = create<SettingsStore>((set) => ({
  ...initial,

  setLightModel: (lightModel) =>
    updateAndPersist(set, { lightModel }),

  setPreferredFallback: (preferredFallback) =>
    updateAndPersist(set, { preferredFallback }),

  addPreSessionHook: (cmd) => {
    const trimmed = cmd.trim();
    if (!trimmed) return;
    set((state) => {
      const preSessionHooks = [...state.preSessionHooks, { cmd: trimmed, enabled: true }];
      persistSettings(toStorable({ ...state, preSessionHooks } as SettingsStore));
      return { preSessionHooks };
    });
  },

  updatePreSessionHook: (index, patch) => {
    set((state) => {
      const preSessionHooks = state.preSessionHooks.map((hook, i) =>
        i === index
          ? {
              cmd: typeof patch.cmd === "string" ? patch.cmd.trim() || hook.cmd : hook.cmd,
              enabled: typeof patch.enabled === "boolean" ? patch.enabled : hook.enabled,
            }
          : hook
      );
      persistSettings(toStorable({ ...state, preSessionHooks } as SettingsStore));
      return { preSessionHooks };
    });
  },

  removePreSessionHook: (index) => {
    set((state) => {
      const preSessionHooks = state.preSessionHooks.filter((_, i) => i !== index);
      persistSettings(toStorable({ ...state, preSessionHooks } as SettingsStore));
      return { preSessionHooks };
    });
  },

  setAutoDispatch: (autoDispatchEnabled) =>
    updateAndPersist(set, { autoDispatchEnabled }),

  setTaskRouting: (task, provider) => {
    set((state) => {
      const taskRouting = { ...state.taskRouting, [task]: provider };
      persistSettings(toStorable({ ...state, taskRouting } as SettingsStore));
      return { taskRouting };
    });
  },

  setPreflightCheck: (name, enabled) => {
    set((state) => {
      const preflightChecks = { ...state.preflightChecks, [name]: enabled };
      persistSettings(toStorable({ ...state, preflightChecks } as SettingsStore));
      return { preflightChecks };
    });
  },

  setSchedulingToggle: (name, enabled) => {
    set((state) => {
      const schedulingToggles = { ...state.schedulingToggles, [name]: enabled };
      persistSettings(toStorable({ ...state, schedulingToggles } as SettingsStore));
      return { schedulingToggles };
    });
  },

  setBranchStrategyToggle: (key, value) => {
    set((state) => {
      const branchStrategyToggles = { ...state.branchStrategyToggles, [key]: value };
      persistSettings(toStorable({ ...state, branchStrategyToggles } as SettingsStore));
      return { branchStrategyToggles };
    });
  },

  addHookToGroup: (group, cmd) => {
    const trimmed = cmd.trim();
    if (!trimmed) return;
    set((state) => {
      const hooks = [...state[group], { cmd: trimmed, enabled: true }];
      persistSettings(toStorable({ ...state, [group]: hooks } as SettingsStore));
      return { [group]: hooks };
    });
  },

  toggleHookInGroup: (group, index) => {
    set((state) => {
      const hooks = state[group].map((hook, i) =>
        i === index ? { ...hook, enabled: !hook.enabled } : hook
      );
      persistSettings(toStorable({ ...state, [group]: hooks } as SettingsStore));
      return { [group]: hooks };
    });
  },

  removeHookFromGroup: (group, index) => {
    set((state) => {
      const hooks = state[group].filter((_, i) => i !== index);
      persistSettings(toStorable({ ...state, [group]: hooks } as SettingsStore));
      return { [group]: hooks };
    });
  },

  setPrePushHookEnabled: (prePushHookEnabled) =>
    updateAndPersist(set, { prePushHookEnabled }),

  setMaxParallelAgents: (maxParallelAgents) =>
    updateAndPersist(set, { maxParallelAgents: Math.max(1, Math.min(8, maxParallelAgents)) }),
}));

function _clampPct(value: unknown, fallback: number): number {
  const parsed = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.max(0, Math.min(100, Math.round(parsed)));
}

function _clampRange(value: unknown, min: number, max: number, fallback: number): number {
  const parsed = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.max(min, Math.min(max, Math.round(parsed)));
}
