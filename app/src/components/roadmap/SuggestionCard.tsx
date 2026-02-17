import { useState } from "react";
import { api } from "../../api/backend";
import type { RoadmapSuggestion } from "../../types";

interface SuggestionCardProps {
  suggestion: RoadmapSuggestion;
  checked: boolean;
  onToggle: () => void;
  projectId: string;
}

export function SuggestionCard({
  suggestion,
  checked,
  onToggle,
  projectId,
}: SuggestionCardProps) {
  const [expanded, setExpanded] = useState(false);
  const [showDiff, setShowDiff] = useState(false);
  const [diffContent, setDiffContent] = useState<string | null>(null);
  const [loadingDiff, setLoadingDiff] = useState(false);

  const confidenceColorClass =
    suggestion.confidence >= 0.8
      ? "text-mc-green"
      : suggestion.confidence >= 0.5
      ? "text-mc-amber"
      : "text-mc-text-3";

  const confidenceLabel =
    suggestion.confidence >= 0.8
      ? "HIGH"
      : suggestion.confidence >= 0.5
      ? "MEDIUM"
      : "LOW";

  const handleViewDiff = async () => {
    if (showDiff) {
      setShowDiff(false);
      return;
    }

    if (!diffContent && suggestion.matched_commits.length > 0) {
      setLoadingDiff(true);
      try {
        // Get diff for first matched commit
        const result = await api.getCommitDiff(projectId, suggestion.matched_commits[0]);
        setDiffContent(result.diff);
        setShowDiff(true);
      } catch (error) {
        console.error("Failed to load diff:", error);
        setDiffContent("Failed to load diff");
        setShowDiff(true);
      } finally {
        setLoadingDiff(false);
      }
    } else {
      setShowDiff(true);
    }
  };

  return (
    <div
      className={`rounded-lg p-3.5 transition-all duration-150 ${
        checked
          ? "bg-mc-accent-muted border border-mc-accent-border"
          : "bg-mc-surface-0 border border-mc-border-1"
      }`}
    >
      {/* Header with checkbox */}
      <div className="flex gap-3 items-start">
        <input
          type="checkbox"
          checked={checked}
          onChange={onToggle}
          className="mt-[3px] cursor-pointer w-4 h-4"
        />

        <div className="flex-1">
          {/* Item text */}
          <div className="text-[13px] text-mc-text-0 mb-1.5">
            {suggestion.item_text}
          </div>

          {/* Metadata */}
          <div className="flex items-center gap-2 text-[11px] text-mc-text-3 mb-2">
            <div
              className={`font-mono text-[10px] font-bold uppercase tracking-[0.05em] ${confidenceColorClass}`}
            >
              {confidenceLabel}
            </div>
            <div>•</div>
            <div>{suggestion.milestone_name}</div>
            <div>•</div>
            <div>{Math.round(suggestion.confidence * 100)}% confidence</div>
          </div>

          {/* Evidence summary */}
          <div
            className={`flex gap-2 text-[11px] text-mc-text-2 ${
              expanded ? "mb-2.5" : "mb-0"
            }`}
          >
            {suggestion.matched_files.length > 0 && (
              <div>
                {suggestion.matched_files.length} file
                {suggestion.matched_files.length > 1 ? "s" : ""}
              </div>
            )}
            {suggestion.matched_commits.length > 0 && (
              <>
                <div>•</div>
                <div>
                  {suggestion.matched_commits.length} commit
                  {suggestion.matched_commits.length > 1 ? "s" : ""}
                </div>
              </>
            )}
            {suggestion.session_id && (
              <>
                <div>•</div>
                <div
                  className="text-mc-accent cursor-pointer underline"
                  onClick={() => {
                    // Navigate to Timeline tab with this session
                    console.log("Navigate to session:", suggestion.session_id);
                    // TODO: Wire up navigation
                  }}
                >
                  Session {suggestion.session_id.slice(0, 8)}
                </div>
              </>
            )}
          </div>

          {/* Expand/collapse reasoning */}
          {suggestion.reasoning.length > 0 && (
            <>
              <div className="flex gap-3 mt-2">
                <button
                  onClick={() => setExpanded(!expanded)}
                  className="bg-transparent border-none p-0 font-sans text-[11px] text-mc-accent cursor-pointer"
                >
                  {expanded ? "▼ Hide details" : "▶ View details"}
                </button>

                {suggestion.matched_commits.length > 0 && (
                  <button
                    onClick={handleViewDiff}
                    disabled={loadingDiff}
                    className={`bg-transparent border-none p-0 font-sans text-[11px] cursor-pointer ${
                      loadingDiff
                        ? "text-mc-text-3 !cursor-wait"
                        : "text-mc-accent"
                    }`}
                  >
                    {loadingDiff
                      ? "Loading diff..."
                      : showDiff
                      ? "▼ Hide diff"
                      : "▶ View diff"}
                  </button>
                )}
              </div>

              {expanded && (
                <div className="mt-2.5 p-2.5 bg-mc-surface-2 rounded-md text-[11px] text-mc-text-2 leading-normal">
                  <div className="font-semibold text-mc-text-1 mb-1.5">
                    Evidence:
                  </div>
                  <ul className="m-0 pl-4">
                    {suggestion.reasoning.map((reason, i) => (
                      <li key={i} className="mb-1">
                        {reason}
                      </li>
                    ))}
                  </ul>

                  {suggestion.matched_files.length > 0 && (
                    <div className="mt-2">
                      <div className="font-semibold text-mc-text-1 mb-1">
                        Matched files:
                      </div>
                      <div className="font-mono text-[10px] text-mc-text-3">
                        {suggestion.matched_files.slice(0, 5).map((file, i) => (
                          <div key={i}>{file}</div>
                        ))}
                        {suggestion.matched_files.length > 5 && (
                          <div>
                            ... and {suggestion.matched_files.length - 5} more
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              )}

              {showDiff && diffContent && (
                <div className="mt-2.5 p-2.5 bg-mc-surface-2 rounded-md text-[11px] font-mono text-mc-text-2 max-h-[400px] overflow-y-auto">
                  <div className="font-semibold text-mc-text-1 mb-1.5 font-sans">
                    Diff (Commit {suggestion.matched_commits[0].slice(0, 7)}):
                  </div>
                  <pre className="m-0 whitespace-pre-wrap break-words text-[10px] leading-snug">
                    {diffContent}
                  </pre>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
