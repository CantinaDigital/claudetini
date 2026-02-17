import { Section } from "../ui/Section";
import { SeverityTag } from "../ui/SeverityTag";
import { Button } from "../ui/Button";
import type { Status } from "../../types";

interface QualityIssue {
  severity: Status;
  title: string;
  suggestion: string;
}

interface QualityIssuesProps {
  issues: QualityIssue[];
}

export function QualityIssues({ issues }: QualityIssuesProps) {
  if (issues.length === 0) {
    return (
      <Section label="Quality Issues">
        <div className="py-6 px-4 text-center text-mc-text-3 text-xs">
          No issues found
        </div>
      </Section>
    );
  }

  return (
    <Section label="Quality Issues" right={`${issues.length} issues`}>
      <div className="py-2 px-4">
        {issues.map((issue, i) => (
          <div
            key={i}
            className={`py-3 ${i < issues.length - 1 ? "border-b border-mc-border-0" : ""}`}
          >
            <div className="flex items-start gap-2.5 mb-1.5">
              <SeverityTag status={issue.severity} />
              <span className="text-xs font-semibold text-mc-text-0 flex-1">
                {issue.title}
              </span>
            </div>
            <div className="text-[11px] text-mc-text-3 leading-relaxed">
              {issue.suggestion}
            </div>
            {issue.severity === "fail" && (
              <div className="mt-2">
                <Button small primary>
                  Fix Now
                </Button>
              </div>
            )}
          </div>
        ))}
      </div>
    </Section>
  );
}
