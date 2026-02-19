type TagStatus = "pass" | "warn" | "fail" | "skipped" | "error" | "pending";

interface SeverityTagProps {
  status: TagStatus;
}

const statusMap: Record<TagStatus, { className: string; label: string }> = {
  fail: { className: "bg-mc-red-muted text-mc-red border border-mc-red-border", label: "FAIL" },
  warn: { className: "bg-mc-amber-muted text-mc-amber border border-mc-amber-border", label: "WARN" },
  pass: { className: "bg-mc-green-muted text-mc-green border border-mc-green-border", label: "PASS" },
  skipped: { className: "bg-mc-surface-3 text-mc-text-3 border border-mc-border-1", label: "SKIP" },
  error: { className: "bg-mc-red-muted text-mc-red border border-mc-red-border", label: "ERR" },
  pending: { className: "bg-mc-surface-3 text-mc-text-3 border border-mc-border-1", label: "IDLE" },
};

export function SeverityTag({ status }: SeverityTagProps) {
  const config = statusMap[status] || statusMap.warn;

  return (
    <span className={`mc-severity-tag ${config.className}`}>
      {config.label}
    </span>
  );
}
