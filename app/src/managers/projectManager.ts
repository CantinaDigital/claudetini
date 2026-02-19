import { create } from "zustand";
import { api } from "../api/backend";
import type { Project, ReadinessReport } from "../types";

// Screen types for app state machine
type AppScreen = "picker" | "scorecard" | "bootstrap" | "dashboard";

// localStorage persistence key for navigation state
const NAV_STORAGE_KEY = "claudetini.navigation.v1";

interface PersistedNavState {
  currentScreen: AppScreen;
  currentProjectPath: string | null;
}

function loadNavState(): PersistedNavState | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(NAV_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<PersistedNavState>;
    // Only restore if the screen value is valid
    if (
      parsed.currentScreen === "picker" ||
      parsed.currentScreen === "scorecard" ||
      parsed.currentScreen === "bootstrap" ||
      parsed.currentScreen === "dashboard"
    ) {
      return {
        currentScreen: parsed.currentScreen,
        currentProjectPath: typeof parsed.currentProjectPath === "string" ? parsed.currentProjectPath : null,
      };
    }
  } catch { /* ignore parse errors */ }
  return null;
}

function persistNavState(screen: AppScreen, projectPath: string | null): void {
  if (typeof window === "undefined") return;
  try {
    const state: PersistedNavState = { currentScreen: screen, currentProjectPath: projectPath };
    window.localStorage.setItem(NAV_STORAGE_KEY, JSON.stringify(state));
  } catch { /* quota or unavailable */ }
}

// Determine initial screen from localStorage
function getInitialScreen(): AppScreen {
  const saved = loadNavState();
  if (saved && saved.currentProjectPath && saved.currentScreen === "dashboard") {
    return "dashboard";
  }
  return "picker";
}

interface ProjectManagerState {
  // Screen state machine
  currentScreen: AppScreen;
  currentProject: Project | null;
  projects: Project[];

  // Readiness state
  readinessScore: number | null;
  readinessReport: ReadinessReport | null;

  // Bootstrap state
  bootstrapSessionId: string | null;
  bootstrapInProgress: boolean;

  // Loading/error
  isLoading: boolean;
  error: string | null;

  // Actions
  setScreen: (screen: AppScreen) => void;
  switchProject: () => void;
  restoreProject: (projects: Project[]) => void;
  loadProjects: () => Promise<void>;
  scanReadiness: (projectPath: string) => Promise<void>;
  startBootstrap: (projectPath: string) => Promise<void>;
  completeBootstrap: () => void;
}

export const useProjectManager = create<ProjectManagerState>((set, get) => ({
  currentScreen: getInitialScreen(),
  currentProject: null,
  projects: [],
  readinessScore: null,
  readinessReport: null,
  bootstrapSessionId: null,
  bootstrapInProgress: false,
  isLoading: false,
  error: null,

  setScreen: (screen) => {
    const projectPath = get().currentProject?.path ?? null;
    persistNavState(screen, projectPath);
    set({ currentScreen: screen });
  },

  switchProject: () => {
    persistNavState("picker", null);
    set({
      currentScreen: "picker",
      currentProject: null,
      readinessScore: null,
      readinessReport: null,
      bootstrapSessionId: null,
      bootstrapInProgress: false,
      error: null,
    });
  },

  restoreProject: (projects) => {
    const saved = loadNavState();
    if (!saved || !saved.currentProjectPath || saved.currentScreen !== "dashboard") return;
    const match = projects.find((p) => p.path === saved.currentProjectPath);
    if (match) {
      set({ currentProject: match, currentScreen: "dashboard" });
    } else {
      // Saved project no longer registered — fall back to picker
      persistNavState("picker", null);
      set({ currentScreen: "picker", currentProject: null });
    }
  },

  loadProjects: async () => {
    set({ isLoading: true, error: null });
    try {
      const projects = await api.listProjects();
      set({ projects, isLoading: false });
      // Attempt to restore persisted project after loading
      get().restoreProject(projects);
    } catch (error) {
      set({ error: String(error), isLoading: false });
    }
  },

  scanReadiness: async (projectPath) => {
    set({ isLoading: true, error: null });
    try {
      const report = await api.scanReadiness(projectPath);
      set({
        readinessScore: report.score,
        readinessReport: report,
        isLoading: false,
      });
    } catch (error) {
      set({ error: String(error), isLoading: false });
    }
  },

  startBootstrap: async (projectPath) => {
    set({ bootstrapInProgress: true, error: null });
    try {
      const data = await api.startBootstrap(projectPath);
      set({ bootstrapSessionId: data.session_id });
    } catch (error) {
      set({ error: String(error), bootstrapInProgress: false });
    }
  },

  completeBootstrap: () => {
    set({
      bootstrapInProgress: false,
      bootstrapSessionId: null,
      currentScreen: "dashboard",
    });
    const projectPath = get().currentProject?.path ?? null;
    persistNavState("dashboard", projectPath);
  },
}));
