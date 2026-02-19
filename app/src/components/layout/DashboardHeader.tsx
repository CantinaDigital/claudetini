import { useCallback, useEffect, useRef, useState } from "react";
import { TabBar } from "./TabBar";
import { Icons } from "../ui/Icons";
import { useProjectManager } from "../../managers/projectManager";
import type { HealthReport } from "../../types";

interface DashboardHeaderProps {
  tabs: string[];
  activeTab: number;
  onTabChange: (index: number) => void;
}

const HEALTH_CACHE_KEY = "claudetini.health-cache";

function loadHealthCache(): Record<string, HealthReport> {
  try {
    const raw = localStorage.getItem(HEALTH_CACHE_KEY);
    if (raw) return JSON.parse(raw);
  } catch { /* ignore */ }
  return {};
}

function truncatePath(path: string, maxLen = 45): string {
  if (path.length <= maxLen) return path;
  return "..." + path.slice(path.length - maxLen + 3);
}

function healthDotColor(score: number | null): string {
  if (score === null) return "bg-mc-text-3"; // gray
  if (score >= 80) return "bg-mc-green";
  if (score >= 50) return "bg-mc-amber";
  return "bg-mc-red";
}

export function DashboardHeader({ tabs, activeTab, onTabChange }: DashboardHeaderProps) {
  const currentProject = useProjectManager((s) => s.currentProject);
  const projects = useProjectManager((s) => s.projects);
  const switchProject = useProjectManager((s) => s.switchProject);
  const setScreen = useProjectManager((s) => s.setScreen);

  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [healthCache, setHealthCache] = useState<Record<string, HealthReport>>(loadHealthCache);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Refresh health cache when dropdown opens
  useEffect(() => {
    if (dropdownOpen) {
      setHealthCache(loadHealthCache());
    }
  }, [dropdownOpen]);

  // Close dropdown on outside click
  useEffect(() => {
    if (!dropdownOpen) return;
    const handleClick = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setDropdownOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [dropdownOpen]);

  // Close dropdown on Escape
  useEffect(() => {
    if (!dropdownOpen) return;
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setDropdownOpen(false);
    };
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [dropdownOpen]);

  const handleSelectProject = useCallback(
    (project: typeof projects[number]) => {
      setDropdownOpen(false);
      // If selecting the same project, just close the dropdown
      if (project.id === currentProject?.id) return;
      // Clear stale project-scoped state, set the new project, and go to dashboard
      useProjectManager.setState({
        currentProject: project,
        readinessScore: null,
        readinessReport: null,
        bootstrapSessionId: null,
        bootstrapInProgress: false,
        error: null,
      });
      setScreen("dashboard");
    },
    [currentProject?.id, setScreen],
  );

  const handleSwitchToPickerView = useCallback(() => {
    setDropdownOpen(false);
    switchProject();
  }, [switchProject]);

  return (
    <div className="bg-mc-surface-0">
      {/* Project name row */}
      <div className="flex items-center px-6 pt-3 pb-1" ref={dropdownRef}>
        <div className="relative">
          <button
            onClick={() => setDropdownOpen((prev) => !prev)}
            className="flex items-center gap-1.5 bg-transparent border-none cursor-pointer p-0 group"
          >
            <span className="text-sm font-bold text-mc-text-0 group-hover:text-mc-accent transition-colors duration-150">
              {currentProject?.name ?? "No Project"}
            </span>
            <span className="text-mc-text-3 group-hover:text-mc-accent transition-colors duration-150">
              {Icons.chevDown({ size: 10, open: dropdownOpen })}
            </span>
          </button>

          {/* Dropdown */}
          {dropdownOpen && (
            <div className="absolute top-full left-0 mt-1.5 w-[340px] max-h-[360px] overflow-y-auto rounded-lg bg-mc-surface-2 border border-mc-border-2 shadow-lg z-50">
              {projects.length === 0 ? (
                <div className="px-4 py-3 text-xs text-mc-text-3">No projects registered</div>
              ) : (
                projects.map((project) => {
                  const isActive = project.id === currentProject?.id;
                  const health = healthCache[project.id];
                  const score = health?.score ?? null;

                  return (
                    <button
                      key={project.id}
                      onClick={() => handleSelectProject(project)}
                      className={`w-full text-left px-4 py-2.5 border-none cursor-pointer transition-colors duration-100 flex items-start gap-2.5 ${
                        isActive
                          ? "bg-mc-accent-muted"
                          : "bg-transparent hover:bg-mc-surface-3"
                      }`}
                    >
                      {/* Health dot */}
                      <span
                        className={`mt-[5px] shrink-0 w-2 h-2 rounded-full ${healthDotColor(score)}`}
                      />

                      {/* Project info */}
                      <div className="flex-1 min-w-0">
                        <div className={`text-xs font-semibold truncate ${isActive ? "text-mc-accent" : "text-mc-text-0"}`}>
                          {project.name}
                        </div>
                        <div className="text-[10px] font-mono text-mc-text-3 truncate">
                          {truncatePath(project.path)}
                        </div>
                      </div>
                    </button>
                  );
                })
              )}

              {/* Separator + All Projects link */}
              <div className="border-t border-mc-border-1">
                <button
                  onClick={handleSwitchToPickerView}
                  className="w-full text-left px-4 py-2.5 bg-transparent border-none cursor-pointer text-xs text-mc-text-2 hover:text-mc-accent hover:bg-mc-surface-3 transition-colors duration-100"
                >
                  All Projects...
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Tab bar */}
      <TabBar tabs={tabs} activeTab={activeTab} onTabChange={onTabChange} />
    </div>
  );
}
