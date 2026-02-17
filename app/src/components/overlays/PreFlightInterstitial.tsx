import { StatusDot } from "../ui/StatusDot";
import { Button } from "../ui/Button";
import { Icons } from "../ui/Icons";
import type { Status } from "../../types";

export interface PreFlightCheck {
  name: string;
  status: Status;
  detail: string;
}

export interface PreSessionHook {
  cmd: string;
  enabled: boolean;
}

export interface PreFlightInputs {
  uncommittedCount: number;
  branch?: string | null;
  dependenciesFresh?: boolean | null;
  previousSessionStatus?: "pass" | "warn" | "fail" | null;
  editorConflict?: boolean | null;
}

interface PreFlightInterstitialProps {
  checks: PreFlightCheck[];
  hooks?: PreSessionHook[];
  prompt?: string;
  mode?: string;
  onClose: () => void;
  onDispatch: () => void;
}

// Generate default checks based on project state.
// Always includes all 5 checks — unavailable data shown as "warn" with explanatory detail.
export function generatePreFlightChecks(inputs: PreFlightInputs): PreFlightCheck[] {
  const {
    uncommittedCount,
    branch,
    dependenciesFresh = null,
    previousSessionStatus = null,
    editorConflict = null,
  } = inputs;

  const branchName = branch && branch.trim().length > 0 ? branch : null;

  return [
    // 1. Uncommitted changes — informational
    {
      name: "Uncommitted changes",
      status: "pass" as const,
      detail: uncommittedCount > 0 ? `${uncommittedCount} files modified` : "Clean",
    },
    // 2. Branch status
    {
      name: "Branch status",
      status: branchName ? "pass" as const : "warn" as const,
      detail: branchName ? `On ${branchName}` : "Active branch unavailable",
    },
    // 3. Dependencies fresh
    {
      name: "Dependencies fresh",
      status: dependenciesFresh != null
        ? (dependenciesFresh ? "pass" as const : "warn" as const)
        : "warn" as const,
      detail: dependenciesFresh != null
        ? (dependenciesFresh ? "Dependency state is current" : "Dependencies may be stale")
        : "Freshness check unavailable",
    },
    // 4. Previous session
    {
      name: "Previous session",
      status: previousSessionStatus != null ? previousSessionStatus : "warn" as const,
      detail: previousSessionStatus != null
        ? (previousSessionStatus === "pass"
          ? "Last session completed successfully"
          : previousSessionStatus === "fail"
          ? "Last session had failures"
          : "Last session requires attention")
        : "No recent session outcome available",
    },
    // 5. Editor conflicts
    {
      name: "Editor conflicts",
      status: editorConflict != null
        ? (editorConflict ? "warn" as const : "pass" as const)
        : "warn" as const,
      detail: editorConflict != null
        ? (editorConflict ? "Recent edits detected; review before dispatch" : "No recent file modification conflicts")
        : "Recent edit activity unavailable",
    },
  ];
}

export function PreFlightInterstitial({
  checks,
  hooks = [],
  prompt,
  mode,
  onClose,
  onDispatch,
}: PreFlightInterstitialProps) {
  const loading = checks.length === 0;
  const hasWarn = checks.some((c) => c.status === "warn");
  const hasFail = checks.some((c) => c.status === "fail");
  const allClear = !loading && !hasWarn && !hasFail;
  const enabledHooks = hooks.filter((h) => h.enabled);

  return (
    <div
      className="fixed inset-0 bg-black/60 z-[100] flex items-center justify-center"
      onClick={onClose}
    >
      <div
        className="w-[460px] bg-mc-surface-1 rounded-[14px] border border-mc-border-1 animate-fade-in-fast overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="px-5 py-[18px] border-b border-mc-border-0">
          <div className="text-[15px] font-bold text-mc-text-0">
            Pre-Flight Checks
          </div>
          <div className="text-[11px] text-mc-text-3 mt-0.5">
            Verifying project state before dispatch...
          </div>
        </div>

        {/* Dispatch Context (if provided) */}
        {prompt && (
          <div className="px-5 py-3 border-b border-mc-border-0 bg-mc-surface-0">
            <div className="mc-label mb-1.5">
              Dispatch Command
            </div>
            <div className="text-xs text-mc-text-1 leading-[1.4] mb-1">
              {prompt.length > 120 ? prompt.substring(0, 120) + "..." : prompt}
            </div>
            {mode && mode !== "standard" && (
              <span className="text-[10px] font-mono font-semibold text-mc-accent bg-mc-accent-muted px-1.5 py-0.5 rounded">
                {mode.replace("-", " ").toUpperCase()}
              </span>
            )}
          </div>
        )}

        {/* Checks */}
        <div className="py-2">
          {loading ? (
            <div className="px-5 py-3 text-xs text-mc-text-3">
              Running checks...
            </div>
          ) : (
            checks.map((check, i) => (
              <div
                key={i}
                className={`flex items-center gap-2.5 px-5 py-2 ${
                  check.status === "warn"
                    ? "bg-mc-amber-muted"
                    : check.status === "fail"
                    ? "bg-mc-red-muted"
                    : "bg-transparent"
                }`}
              >
                <StatusDot status={check.status} />
                <span className="text-[12.5px] font-medium text-mc-text-1 flex-1">
                  {check.name}
                </span>
                <span
                  className={`text-[11px] font-mono ${
                    check.status === "pass"
                      ? "text-mc-text-3"
                      : check.status === "warn"
                      ? "text-mc-amber"
                      : "text-mc-red"
                  }`}
                >
                  {check.detail}
                </span>
              </div>
            ))
          )}
        </div>

        {/* Pre-Session Hooks (F17) */}
        {enabledHooks.length > 0 && (
          <div className="px-5 pt-2 pb-3 border-t border-mc-border-0">
            <div className="mc-label mb-1.5">
              Pre-Session Hooks
            </div>
            {enabledHooks.map((hook, i) => (
              <div
                key={i}
                className="text-[11px] font-mono text-mc-text-2 py-0.5"
              >
                → {hook.cmd}
              </div>
            ))}
          </div>
        )}

        {/* Actions */}
        <div className="flex gap-2 px-5 py-3.5 border-t border-mc-border-0">
          <Button small onClick={onClose}>
            Cancel
          </Button>
          <div className="flex-1" />
          {loading ? (
            <Button
              primary
              onClick={undefined}
              className="opacity-50 pointer-events-none"
            >
              Checking...
            </Button>
          ) : hasFail ? (
            <Button
              primary
              onClick={undefined}
              className="opacity-50 pointer-events-none"
            >
              Blocked
            </Button>
          ) : (
            <Button primary onClick={onDispatch}>
              <Icons.play size={10} />{" "}
              {allClear ? "Dispatch" : "Dispatch Anyway"}
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
