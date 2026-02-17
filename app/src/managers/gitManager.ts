import { create } from "zustand";
import { api } from "../api/backend";
import type { GitStatus, Commit } from "../types";

interface GitManagerState {
  status: GitStatus | null;
  commits: Commit[];
  loading: boolean;
  error: string | null;
  commitMessage: string;
  isCommitting: boolean;
  isGeneratingMessage: boolean;

  // Actions
  refresh: (projectId: string) => Promise<void>;
  stageFiles: (projectId: string, files: string[]) => Promise<void>;
  stageAll: (projectId: string) => Promise<void>;
  unstageFiles: (projectId: string, files: string[]) => Promise<void>;
  unstageAll: (projectId: string) => Promise<void>;
  setCommitMessage: (msg: string) => void;
  generateMessage: (projectId: string) => Promise<void>;
  generateMessageAI: (projectId: string) => Promise<void>;
  commit: (projectId: string) => Promise<boolean>;
  push: (projectId: string) => Promise<boolean>;
  stashPop: (projectId: string) => Promise<void>;
  stashDrop: (projectId: string, stashId?: string) => Promise<void>;
  discardFile: (projectId: string, file: string) => Promise<void>;
  deleteUntracked: (projectId: string, file: string) => Promise<void>;
}

export const useGitManager = create<GitManagerState>((set, get) => ({
  status: null,
  commits: [],
  loading: false,
  error: null,
  commitMessage: "",
  isCommitting: false,
  isGeneratingMessage: false,

  refresh: async (projectId) => {
    set({ loading: true, error: null });
    try {
      const [status, commits] = await Promise.all([
        api.getGitStatus(projectId),
        api.getCommits(projectId),
      ]);
      set({ status, commits, loading: false });
    } catch (error) {
      set({ error: String(error), loading: false });
    }
  },

  stageFiles: async (projectId, files) => {
    try {
      await api.stageFiles(projectId, files);
      await get().refresh(projectId);
    } catch (error) {
      set({ error: String(error) });
    }
  },

  stageAll: async (projectId) => {
    try {
      await api.stageAll(projectId);
      await get().refresh(projectId);
    } catch (error) {
      set({ error: String(error) });
    }
  },

  unstageFiles: async (projectId, files) => {
    try {
      await api.unstageFiles(projectId, files);
      await get().refresh(projectId);
    } catch (error) {
      set({ error: String(error) });
    }
  },

  unstageAll: async (projectId) => {
    try {
      await api.unstageAll(projectId);
      await get().refresh(projectId);
    } catch (error) {
      set({ error: String(error) });
    }
  },

  setCommitMessage: (msg) => set({ commitMessage: msg }),

  generateMessage: async (projectId) => {
    set({ isGeneratingMessage: true });
    try {
      const result = await api.generateCommitMessage(projectId);
      set({ commitMessage: result.message, isGeneratingMessage: false });
    } catch (error) {
      set({ error: String(error), isGeneratingMessage: false });
    }
  },

  generateMessageAI: async (projectId) => {
    set({ isGeneratingMessage: true });
    try {
      const result = await api.generateCommitMessageAI(projectId);
      set({ commitMessage: result.message, isGeneratingMessage: false });
    } catch (error) {
      set({ error: String(error), isGeneratingMessage: false });
    }
  },

  commit: async (projectId) => {
    const { commitMessage } = get();
    if (!commitMessage.trim()) return false;

    set({ isCommitting: true });
    try {
      const result = await api.commitStaged(projectId, commitMessage);
      if (result.success) {
        set({ commitMessage: "", isCommitting: false });
        await get().refresh(projectId);
        return true;
      }
      set({ error: result.message, isCommitting: false });
      return false;
    } catch (error) {
      set({ error: String(error), isCommitting: false });
      return false;
    }
  },

  push: async (projectId) => {
    try {
      const result = await api.pushToRemote(projectId);
      if (result.success) {
        await get().refresh(projectId);
        return true;
      }
      set({ error: result.message });
      return false;
    } catch (error) {
      set({ error: String(error) });
      return false;
    }
  },

  stashPop: async (projectId) => {
    try {
      await api.stashPop(projectId);
      await get().refresh(projectId);
    } catch (error) {
      set({ error: String(error) });
    }
  },

  stashDrop: async (projectId, stashId) => {
    try {
      await api.stashDrop(projectId, stashId);
      await get().refresh(projectId);
    } catch (error) {
      set({ error: String(error) });
    }
  },

  discardFile: async (projectId, file) => {
    try {
      await api.discardFile(projectId, file);
      await get().refresh(projectId);
    } catch (error) {
      set({ error: String(error) });
    }
  },

  deleteUntracked: async (projectId, file) => {
    try {
      await api.deleteUntracked(projectId, file);
      await get().refresh(projectId);
    } catch (error) {
      set({ error: String(error) });
    }
  },
}));
