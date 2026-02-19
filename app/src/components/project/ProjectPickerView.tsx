import { useMemo, useState, useEffect, useRef, type FormEvent } from "react";
import { Button } from "../ui/Button";
import { Tag } from "../ui/Tag";
import { Icons } from "../ui/Icons";
import { ReadinessRing, scoreColor } from "../scorecard/ReadinessRing";
import { api, isBackendConnected as checkBackend } from "../../api/backend";
import type { Project, DiscoveredProject, HealthReport, TimelineEntry } from "../../types";

interface ProjectPickerViewProps {
  projects: Project[];
  selectedProjectId?: string | null;
  loading?: boolean;
  registering?: boolean;
  backendConnected?: boolean;
  error?: string | null;
  onSelectProject: (project: Project) => void;
  onOpenProject: (project: Project) => void;
  onRegisterProject: (path: string) => void | Promise<void>;
  onRefresh?: () => void;
}

function normalize(value: string): string {
  return value.trim().toLowerCase();
}

function matchesQuery(project: Project, query: string): boolean {
  if (!query) return true;
  const searchSpace = [
    project.name,
    project.path,
    project.branch,
    project.lastSession || "",
    project.readmeSummary || "",
  ];
  return searchSpace.some((value) => normalize(value).includes(query));
}

function uncommittedLabel(count: number): string {
  if (count === 0) return "Clean";
  if (count === 1) return "1 change";
  return `${count} changes`;
}

function statLabel(value: string | null | undefined, fallback = "N/A"): string {
  if (!value || !value.trim()) return fallback;
  return value;
}

export function ProjectPickerView({
  projects,
  selectedProjectId = null,
  loading = false,
  registering = false,
  backendConnected = true,
  error = null,
  onSelectProject,
  onOpenProject,
  onRegisterProject,
  onRefresh,
}: ProjectPickerViewProps) {
  const [query, setQuery] = useState("");
  const [projectPathInput, setProjectPathInput] = useState("");
  const [pathError, setPathError] = useState<string | null>(null);
  const [discovered, setDiscovered] = useState<DiscoveredProject[]>([]);
  const [discovering, setDiscovering] = useState(false);
  const [discoveryOpen, setDiscoveryOpen] = useState(true);
  const [healthMap, setHealthMap] = useState<Record<string, HealthReport>>(() => {
    // Load cached health scores from localStorage on mount
    try {
      const cached = localStorage.getItem("claudetini.health-cache");
      if (cached) return JSON.parse(cached);
    } catch { /* ignore parse errors */ }
    return {};
  });
  const [timelineEntries, setTimelineEntries] = useState<TimelineEntry[]>([]);
  const healthFetchedRef = useRef<string>("");

  const queryValue = normalize(query);

  const filteredProjects = useMemo(() => {
    const filtered = projects.filter((project) => matchesQuery(project, queryValue));
    return filtered.sort((a, b) => {
      if (a.lastOpenedTimestamp && !b.lastOpenedTimestamp) return -1;
      if (!a.lastOpenedTimestamp && b.lastOpenedTimestamp) return 1;
      if (a.lastOpenedTimestamp && b.lastOpenedTimestamp) {
        return new Date(b.lastOpenedTimestamp).getTime() - new Date(a.lastOpenedTimestamp).getTime();
      }
      return a.name.localeCompare(b.name);
    });
  }, [projects, queryValue]);

  const selectedProject = useMemo(() => {
    if (filteredProjects.length === 0) return null;
    if (!selectedProjectId) return filteredProjects[0];
    return filteredProjects.find((project) => project.id === selectedProjectId) || filteredProjects[0];
  }, [filteredProjects, selectedProjectId]);

  const handleRegisterProject = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const nextPath = projectPathInput.trim();
    if (!nextPath) {
      setPathError("Enter a local filesystem path.");
      return;
    }
    setPathError(null);
    await onRegisterProject(nextPath);
    setProjectPathInput("");
  };

  const handleOpenSelected = () => {
    if (!selectedProject) return;
    onOpenProject(selectedProject);
  };

  const handleDiscover = async () => {
    if (!backendConnected || !checkBackend()) return;
    setDiscovering(true);
    try {
      const results = await api.discoverProjects();
      // 8.5 dedup: filter out paths already registered
      const registeredPaths = new Set(projects.map((p) => p.path));
      setDiscovered(results.filter((d) => !registeredPaths.has(d.path)));
    } catch {
      setDiscovered([]);
    } finally {
      setDiscovering(false);
    }
  };

  const handleRegisterDiscovered = async (path: string) => {
    try {
      await onRegisterProject(path);
      // Remove from discovered list only on success
      setDiscovered((prev) => prev.filter((d) => d.path !== path));
    } catch {
      // Registration failed — keep the project in discovered list so user can retry
    }
  };

  // Keyboard navigation
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement) return;
      if (filteredProjects.length === 0) return;

      const currentIndex = selectedProject
        ? filteredProjects.findIndex((p) => p.id === selectedProject.id)
        : 0;

      switch (event.key) {
        case "ArrowDown":
          event.preventDefault();
          if (currentIndex < filteredProjects.length - 1) onSelectProject(filteredProjects[currentIndex + 1]);
          break;
        case "ArrowUp":
          event.preventDefault();
          if (currentIndex > 0) onSelectProject(filteredProjects[currentIndex - 1]);
          break;
        case "Enter":
          event.preventDefault();
          handleOpenSelected();
          break;
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [filteredProjects, selectedProject, onSelectProject, handleOpenSelected]);

  // Fetch health data only for the selected project (not all projects).
  // Cached scores from localStorage are used for non-selected project cards.
  useEffect(() => {
    if (!backendConnected || !checkBackend() || !selectedProject) return;
    // Skip if we already fetched health for this project
    if (healthFetchedRef.current === selectedProject.id) return;
    healthFetchedRef.current = selectedProject.id;

    const fetchHealth = async () => {
      try {
        const health = await api.getProjectHealth(selectedProject.id);
        setHealthMap((prev) => {
          const next = { ...prev, [selectedProject.id]: health };
          try { localStorage.setItem("claudetini.health-cache", JSON.stringify(next)); } catch { /* quota */ }
          return next;
        });
      } catch {
        // Non-critical — cached values remain
      }
    };
    void fetchHealth();
  }, [selectedProject?.id, backendConnected]);

  // Fetch timeline entries for the selected project
  useEffect(() => {
    if (!selectedProject || !backendConnected || !checkBackend()) {
      setTimelineEntries([]);
      return;
    }
    let cancelled = false;
    const fetchTimeline = async () => {
      try {
        const resp = await api.getTimeline(selectedProject.id, 3);
        if (!cancelled) setTimelineEntries(resp.entries);
      } catch {
        if (!cancelled) setTimelineEntries([]);
      }
    };
    void fetchTimeline();
    return () => { cancelled = true; };
  }, [selectedProject?.id, backendConnected]);

  // Derive health data for the selected project
  const selectedHealth = selectedProject ? healthMap[selectedProject.id] : null;
  const healthItems = selectedHealth?.items || [];
  const healthScore = selectedHealth?.score ?? null;
  const passedChecks = healthItems.filter((i) => i.status === "pass").length;
  const totalChecks = healthItems.length;

  // Recent sessions from real timeline data
  const recentSessions = timelineEntries.slice(0, 3).map((entry, i) => ({
    id: i + 1,
    sessionId: entry.sessionId,
    summary: entry.summary || "Session activity",
    time: entry.date || "unknown",
  }));

  return (
    <div className="flex min-h-screen bg-mc-bg text-mc-text-1 font-sans">
      {/* LEFT PANEL: Project List */}
      <div className="w-[440px] border-r border-mc-border-1 px-6 py-7 flex flex-col gap-4 bg-mc-surface-0">
        {/* Header */}
        <div>
          <h1 className="text-[22px] font-extrabold text-mc-text-0 m-0 tracking-[-0.03em]">
            Select Project
          </h1>
          <p className="text-xs text-mc-text-3 mt-1 mb-0 font-sans">
            Pick a registered workspace or add a new path.
          </p>
        </div>

        {!backendConnected && (
          <div className="px-2.5 py-2 rounded-md border border-mc-amber-border bg-mc-amber-muted text-mc-amber text-[11.5px]">
            Backend not connected. Start sidecar to manage projects.
          </div>
        )}

        {/* Search + Refresh */}
        <div className="flex gap-2">
          <div className="flex-1 flex items-center gap-2 px-3 py-2 rounded-lg bg-mc-surface-2 border border-mc-border-1">
            <span className="text-mc-text-3 shrink-0">{Icons.search({ size: 12 })}</span>
            <input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search by name, path, or branch..."
              className="flex-1 bg-transparent border-none outline-none text-mc-text-0 text-xs font-sans"
            />
          </div>
          {onRefresh && (
            <Button small onClick={() => onRefresh()} disabled={loading || !backendConnected}>
              {Icons.refresh({ size: 11 })} Refresh
            </Button>
          )}
        </div>

        {/* Project Cards */}
        <div className="flex-1 overflow-y-auto flex flex-col gap-1.5">
          {loading && (
            <div className="p-[22px] text-center text-xs text-mc-text-2">
              Loading projects...
            </div>
          )}

          {!loading && error && (
            <div className="m-2 rounded-lg border border-mc-red-border bg-mc-red-muted p-3 text-mc-red text-xs">
              {error}
            </div>
          )}

          {!loading && !error && filteredProjects.length === 0 && (
            <div className="m-2 rounded-lg border border-dashed border-mc-border-2 px-3 py-4 text-xs text-mc-text-2 text-center">
              {projects.length === 0 ? "No registered projects yet." : `No projects match "${query}"`}
            </div>
          )}

          {!loading &&
            !error &&
            filteredProjects.map((project) => {
              const isSelected = selectedProject?.id === project.id;
              const projectHealth = healthMap[project.id];
              const readiness = projectHealth?.score ?? null;
              const rc = readiness != null ? scoreColor(readiness) : "#5c5c6e";

              return (
                <div
                  key={project.id}
                  onClick={() => onSelectProject(project)}
                  onDoubleClick={() => onOpenProject(project)}
                  className={`px-4 py-3.5 rounded-[10px] cursor-pointer transition-all ${
                    isSelected
                      ? "bg-mc-accent-muted border-[1.5px] border-mc-accent-border"
                      : "bg-mc-surface-1 border border-mc-border-0"
                  }`}
                >
                  {/* Top row: folder icon + name + status tag */}
                  <div className="flex justify-between items-start mb-1.5">
                    <div className="flex items-center gap-2">
                      <span className={isSelected ? "text-mc-accent" : "text-mc-text-2"}>{Icons.folder({ size: 13 })}</span>
                      <span className={`text-sm font-bold ${isSelected ? "text-mc-text-0" : "text-mc-text-1"}`}>
                        {project.name}
                      </span>
                    </div>
                    <div className="flex gap-[5px]">
                      {project.uncommitted === 0 ? (
                        <Tag color="#34d399" bg="rgba(52,211,153,0.1)">Clean</Tag>
                      ) : (
                        <Tag color="#fbbf24" bg="rgba(251,191,36,0.08)">{uncommittedLabel(project.uncommitted)}</Tag>
                      )}
                    </div>
                  </div>

                  {/* Path */}
                  <div className="text-[10px] font-mono text-mc-text-3 mb-1.5 overflow-hidden text-ellipsis whitespace-nowrap">
                    {project.path}
                  </div>

                  {/* Bottom row: branch + mini readiness bar + opened time */}
                  <div className="flex items-center gap-2.5 text-[10px] font-mono text-mc-text-3">
                    <span className="flex items-center gap-[3px] text-mc-text-2">
                      {Icons.branch({ size: 11 })} {statLabel(project.branch, "unknown")}
                    </span>
                    <div className="w-px h-2.5 bg-mc-border-1" />
                    {/* Mini readiness bar */}
                    <div className="flex items-center gap-1">
                      <div className="w-8 h-[3px] bg-mc-surface-3 rounded-sm overflow-hidden">
                        <div
                          className="h-full rounded-sm"
                          style={{ width: `${readiness ?? 0}%`, background: rc }}
                        />
                      </div>
                      <span className="font-semibold" style={{ color: rc }}>{readiness ?? "—"}</span>
                    </div>
                    <div className="flex-1" />
                    <span>{project.lastOpened ? `Opened ${project.lastOpened}` : "Never opened"}</span>
                  </div>
                </div>
              );
            })}
        </div>

        {/* Auto-discover section */}
        <div className="border-t border-mc-border-1 pt-3">
          <div className="flex items-center justify-between mb-2">
            <span className="text-[10px] font-semibold font-mono text-mc-text-3 uppercase tracking-[0.06em]">
              Auto-discovered from Claude Code
            </span>
            <Button
              small
              onClick={() => void handleDiscover()}
              disabled={discovering || !backendConnected}
            >
              {discovering ? (
                <>
                  <span className="inline-block w-3 h-3 border-[1.5px] border-mc-text-3 border-t-mc-accent rounded-full animate-spin" />
                  Scanning...
                </>
              ) : (
                <>
                  {Icons.search({ size: 11 })} Discover
                </>
              )}
            </Button>
          </div>

          {discovered.length > 0 && (
            <div>
              <button
                type="button"
                onClick={() => setDiscoveryOpen((o) => !o)}
                className="flex items-center gap-1 text-[10px] text-mc-text-2 mb-1.5 bg-transparent border-none cursor-pointer p-0"
              >
                <span className={`transition-transform ${discoveryOpen ? "rotate-90" : ""}`}>
                  {Icons.play({ size: 8 })}
                </span>
                {discovered.length} project{discovered.length !== 1 ? "s" : ""} found
              </button>

              {discoveryOpen && (
                <div className="flex flex-col gap-1">
                  {discovered.map((d) => (
                    <div
                      key={d.path}
                      className="flex items-center gap-2 px-3 py-2 rounded-lg bg-mc-surface-1 border border-mc-border-0"
                    >
                      <span className="text-mc-text-2">{Icons.folder({ size: 12 })}</span>
                      <div className="flex-1 min-w-0">
                        <div className="text-xs font-bold text-mc-text-1 truncate">{d.name}</div>
                        <div className="text-[9px] font-mono text-mc-text-3 truncate">{d.path}</div>
                      </div>
                      <Button
                        small
                        primary
                        onClick={() => void handleRegisterDiscovered(d.path)}
                        disabled={registering}
                      >
                        Register
                      </Button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {!discovering && discovered.length === 0 && (
            <div className="text-[10px] text-mc-text-3 text-center py-1">
              No unregistered projects found
            </div>
          )}
        </div>

        {/* Add Path */}
        <form
          onSubmit={(event) => void handleRegisterProject(event)}
          className="flex gap-2"
        >
          <div className="flex-1 flex items-center gap-2 px-3 py-2 rounded-lg bg-mc-surface-2 border border-mc-border-1">
            <input
              value={projectPathInput}
              onChange={(e) => setProjectPathInput(e.target.value)}
              placeholder="/path/to/project"
              disabled={registering || !backendConnected}
              className="flex-1 bg-transparent border-none outline-none text-mc-text-0 text-[11px] font-mono"
            />
          </div>
          <Button primary small disabled={registering || !backendConnected}>
            {registering ? "Adding..." : "Add Path"}
          </Button>
        </form>
        {pathError && <div className="text-[11px] text-mc-red -mt-2">{pathError}</div>}
      </div>

      {/* RIGHT PANEL: Project Detail */}
      <div className="flex-1 px-8 py-7 flex flex-col bg-mc-bg">
        {selectedProject ? (
          <>
            {/* Project header */}
            <div className="mb-6">
              <div className="mc-label mb-1.5">
                Project Detail
              </div>
              <h2 className="text-[28px] font-extrabold text-mc-text-0 m-0 tracking-[-0.03em]">
                {selectedProject.name}
              </h2>
              <div className="text-[11px] font-mono text-mc-text-3 mt-1">
                {selectedProject.path}
              </div>
            </div>

            {/* Stats grid */}
            <div className="grid grid-cols-2 gap-2.5 mb-5">
              {[
                { label: "Branch", value: statLabel(selectedProject.branch, "unknown"), icon: Icons.branch({ size: 13, color: "#5c5c6e" }) },
                { label: "Weekly Usage", value: statLabel(selectedProject.costWeek), accent: true },
                { label: "Last Session", value: statLabel(selectedProject.lastSession, "Never") },
                { label: "Sessions", value: String(selectedProject.totalSessions) },
              ].map((s, i) => (
                <div
                  key={i}
                  className="px-4 py-3 rounded-lg bg-mc-surface-1 border border-mc-border-0"
                >
                  <div className="text-[9.5px] font-semibold font-mono text-mc-text-3 uppercase tracking-[0.06em] mb-1">
                    {s.label}
                  </div>
                  <div className={`text-base font-bold font-mono flex items-center gap-1.5 ${s.accent ? "text-mc-accent" : "text-mc-text-0"}`}>
                    {s.icon && <span>{s.icon}</span>}
                    {s.value}
                  </div>
                </div>
              ))}
            </div>

            {/* Readiness preview */}
            <div className="px-5 py-4 rounded-[10px] bg-mc-surface-1 border border-mc-border-0 mb-5">
              <div className="flex items-center justify-between mb-3">
                <div className="mc-label">
                  Readiness
                </div>
                <span className="text-[11px] font-mono text-mc-text-3">
                  {totalChecks > 0 ? `${passedChecks} / ${totalChecks} checks` : "Loading..."}
                </span>
              </div>
              <div className="flex items-center gap-3.5">
                {/* Small score ring */}
                <ReadinessRing score={healthScore ?? 0} size={56} />
                {/* Health check pills */}
                <div className="flex-1 flex flex-wrap gap-1">
                  {healthItems.length > 0 ? (
                    healthItems.map((item) => {
                      const ok = item.status === "pass";
                      const warn = item.status === "warn";
                      return (
                        <span
                          key={item.name}
                          title={item.detail}
                          className={`text-[9.5px] font-mono px-1.5 py-[2px] rounded-[3px] font-medium border ${
                            ok
                              ? "bg-mc-green-muted text-mc-green border-mc-green-border"
                              : warn
                              ? "bg-mc-amber-muted text-mc-amber border-mc-amber-border"
                              : "bg-mc-red-muted text-mc-red border-mc-red-border"
                          }`}
                        >
                          {ok ? "\u2713" : warn ? "!" : "\u2717"} {item.name}
                        </span>
                      );
                    })
                  ) : (
                    <span className="text-[10px] text-mc-text-3">No health data available</span>
                  )}
                </div>
              </div>
            </div>

            {/* README Summary */}
            <div className="px-[18px] py-3.5 rounded-lg bg-mc-surface-1 border border-mc-border-0 mb-5">
              <div className="mc-label mb-1.5">
                Readme Summary
              </div>
              <div className="text-[13px] text-mc-text-1 leading-[1.55]">
                {selectedProject.readmeSummary || "No README summary available."}
              </div>
            </div>

            {/* Recent Activity */}
            {recentSessions.length > 0 && (
              <div className="px-[18px] py-3.5 rounded-lg bg-mc-surface-1 border border-mc-border-0 mb-5">
                <div className="flex items-center justify-between mb-2.5">
                  <div className="mc-label">
                    Recent Activity
                  </div>
                  <span className="text-[10px] font-mono text-mc-text-3">
                    {selectedProject.totalSessions} total
                  </span>
                </div>
                {recentSessions.map((s, i) => (
                  <div
                    key={s.sessionId || i}
                    className={`flex items-center gap-2 py-1.5 ${i > 0 ? "border-t border-mc-border-0" : ""}`}
                  >
                    <span className="text-[10px] font-mono text-mc-accent font-semibold w-7 shrink-0">
                      #{s.id}
                    </span>
                    <span className="text-[11px] text-mc-text-2 flex-1 overflow-hidden text-ellipsis whitespace-nowrap">
                      {s.summary}
                    </span>
                    <span className="text-[10px] font-mono text-mc-text-3 shrink-0">{s.time}</span>
                  </div>
                ))}
              </div>
            )}

            {/* Open Project button -- pinned to bottom */}
            <div className="mt-auto flex justify-end pt-4">
              <Button
                primary
                onClick={handleOpenSelected}
                disabled={!selectedProject || loading || !backendConnected}
                className="!px-7 !py-2.5 !text-sm !rounded-[10px]"
              >
                {Icons.play({ size: 10, color: "#fff" })} Open Project
              </Button>
            </div>
          </>
        ) : (
          <div className="flex-1 flex items-center justify-center text-mc-text-3 text-[13px]">
            Select a project to view details
          </div>
        )}
      </div>
    </div>
  );
}
