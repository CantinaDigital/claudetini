import { create } from "zustand";
import { api } from "../api/backend";
import type { Project, ReadinessReport } from "../types";

// Screen types for app state machine
type AppScreen = "picker" | "scorecard" | "bootstrap" | "dashboard";

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
  loadProjects: () => Promise<void>;
  scanReadiness: (projectPath: string) => Promise<void>;
  startBootstrap: (projectPath: string) => Promise<void>;
  completeBootstrap: () => void;
}

export const useProjectManager = create<ProjectManagerState>((set) => ({
  currentScreen: "picker",
  currentProject: null,
  projects: [],
  readinessScore: null,
  readinessReport: null,
  bootstrapSessionId: null,
  bootstrapInProgress: false,
  isLoading: false,
  error: null,

  setScreen: (screen) => set({ currentScreen: screen }),

  loadProjects: async () => {
    set({ isLoading: true, error: null });
    try {
      const projects = await api.listProjects();
      set({ projects, isLoading: false });
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
  },
}));
