import { useState, useMemo } from "react";
import type { IntegrationMap, IntegrationPoint } from "../../types";
import { Tag } from "../ui/Tag";
import { Icons } from "../ui/Icons";
import { Section } from "../ui/Section";
import { SkeletonCard } from "../ui/SkeletonLoader";
import { t } from "../../styles/tokens";

interface IntegrationsMapProps {
  integrations: IntegrationMap;
  isLoading?: boolean;
}

const typeConfig: Record<
  IntegrationPoint["integration_type"],
  { color: string; bg: string; label: string }
> = {
  external_api: { color: t.red, bg: t.redMuted, label: "API" },
  internal_route: { color: t.cyan, bg: t.cyanMuted, label: "Route" },
  sdk_import: { color: t.green, bg: t.greenMuted, label: "SDK" },
  database: { color: t.accent, bg: t.accentMuted, label: "DB" },
};

function TypeIcon({ type }: { type: IntegrationPoint["integration_type"] }) {
  const color = typeConfig[type]?.color ?? t.text3;
  switch (type) {
    case "external_api":
      return (
        <svg width={14} height={14} viewBox="0 0 14 14" fill="none">
          <circle cx="7" cy="7" r="5.5" stroke={color} strokeWidth="1.2" />
          <path d="M2 7h10M7 2c-2 2-2 8 0 10M7 2c2 2 2 8 0 10" stroke={color} strokeWidth="1" />
        </svg>
      );
    case "internal_route":
      return (
        <svg width={14} height={14} viewBox="0 0 14 14" fill="none">
          <path d="M2 7h4l2-3 2 6 2-3h2" stroke={color} strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      );
    case "sdk_import":
      return (
        <svg width={14} height={14} viewBox="0 0 14 14" fill="none">
          <rect x="2" y="3" width="10" height="8" rx="1.5" stroke={color} strokeWidth="1.2" />
          <path d="M5 6l2 2 2-2" stroke={color} strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      );
    case "database":
      return (
        <svg width={14} height={14} viewBox="0 0 14 14" fill="none">
          <ellipse cx="7" cy="4" rx="5" ry="2" stroke={color} strokeWidth="1.2" />
          <path d="M2 4v6c0 1.1 2.24 2 5 2s5-.9 5-2V4" stroke={color} strokeWidth="1.2" />
          <path d="M2 7c0 1.1 2.24 2 5 2s5-.9 5-2" stroke={color} strokeWidth="1" opacity="0.5" />
        </svg>
      );
  }
}

interface GroupedService {
  service_name: string;
  count: number;
  endpoints: string[];
  files: string[];
  integration_types: Set<IntegrationPoint["integration_type"]>;
  points: IntegrationPoint[];
}

export function IntegrationsMap({ integrations, isLoading = false }: IntegrationsMapProps) {
  const [search, setSearch] = useState("");
  const [expandedService, setExpandedService] = useState<string | null>(null);

  const grouped = useMemo(() => {
    const map = new Map<string, GroupedService>();

    for (const point of integrations.integrations) {
      const existing = map.get(point.service_name);
      if (existing) {
        existing.count++;
        existing.integration_types.add(point.integration_type);
        existing.points.push(point);
        if (point.endpoint_url && !existing.endpoints.includes(point.endpoint_url)) {
          existing.endpoints.push(point.endpoint_url);
        }
        if (!existing.files.includes(point.file_path)) {
          existing.files.push(point.file_path);
        }
      } else {
        map.set(point.service_name, {
          service_name: point.service_name,
          count: 1,
          endpoints: point.endpoint_url ? [point.endpoint_url] : [],
          files: [point.file_path],
          integration_types: new Set([point.integration_type]),
          points: [point],
        });
      }
    }

    // Also include services_detected that might not have individual points
    for (const svc of integrations.services_detected) {
      if (!map.has(svc.service_name)) {
        map.set(svc.service_name, {
          service_name: svc.service_name,
          count: svc.count,
          endpoints: svc.endpoints,
          files: svc.files,
          integration_types: new Set(),
          points: [],
        });
      }
    }

    return Array.from(map.values()).sort((a, b) => b.count - a.count);
  }, [integrations]);

  const filtered = useMemo(() => {
    if (!search.trim()) return grouped;
    const q = search.toLowerCase();
    return grouped.filter((s) => s.service_name.toLowerCase().includes(q));
  }, [grouped, search]);

  if (isLoading) {
    return (
      <Section label="Integrations">
        <div className="p-4 flex flex-col gap-3">
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
        </div>
      </Section>
    );
  }

  if (grouped.length === 0) {
    return (
      <Section label="Integrations" right={`${integrations.files_scanned} files scanned`}>
        <div className="py-6 px-4 text-center text-mc-text-3 text-xs">
          No integrations detected
        </div>
      </Section>
    );
  }

  return (
    <Section
      label="Integrations"
      right={`${grouped.length} services`}
    >
      {/* Search */}
      <div className="px-4 pt-3 pb-2">
        <div className="relative">
          <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-mc-text-3">
            {Icons.search({ size: 11 })}
          </span>
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Filter services..."
            className="w-full bg-mc-surface-2 border border-mc-border-1 rounded-lg text-xs text-mc-text-1 placeholder:text-mc-text-3 py-1.5 pl-8 pr-3 font-mono outline-none focus:border-mc-accent-border transition-colors"
          />
        </div>
      </div>

      {/* Grid */}
      <div className="px-4 pb-4 grid grid-cols-3 gap-2.5">
        {filtered.map((service, idx) => {
          const isExpanded = expandedService === service.service_name;
          const primaryType = service.points[0]?.integration_type ?? "sdk_import";
          const cfg = typeConfig[primaryType];

          return (
            <div
              key={service.service_name}
              style={{ "--stagger-delay": `${idx * 0.02}s` } as React.CSSProperties}
              className="animate-slide-up [animation-delay:var(--stagger-delay)] [animation-fill-mode:both]"
            >
              <button
                type="button"
                onClick={() => setExpandedService(isExpanded ? null : service.service_name)}
                className={`w-full text-left bg-mc-surface-2 border rounded-lg p-3 cursor-pointer transition-colors duration-150 hover:bg-mc-surface-3 ${
                  isExpanded ? "border-mc-border-2" : "border-mc-border-0"
                }`}
              >
                <div className="flex items-start gap-2.5">
                  <span className="flex-shrink-0 mt-0.5">
                    <TypeIcon type={primaryType} />
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-semibold text-mc-text-0 truncate">
                        {service.service_name}
                      </span>
                      <span className="text-[10px] font-mono font-bold text-mc-text-3 flex-shrink-0">
                        {service.count}
                      </span>
                    </div>
                    <div className="flex items-center gap-1 mt-1.5 flex-wrap">
                      {Array.from(service.integration_types).map((itype) => (
                        <Tag key={itype} color={typeConfig[itype].color} bg={typeConfig[itype].bg}>
                          {typeConfig[itype].label}
                        </Tag>
                      ))}
                      {service.integration_types.size === 0 && (
                        <Tag>{`${service.count} points`}</Tag>
                      )}
                    </div>
                  </div>
                  <span className="flex-shrink-0 text-mc-text-3 mt-0.5">
                    {Icons.chevDown({ size: 9, open: isExpanded })}
                  </span>
                </div>
              </button>

              {/* Expanded details */}
              {isExpanded && (
                <div className="mt-1 bg-mc-surface-1 border border-mc-border-0 rounded-lg p-3 animate-fade-in">
                  {/* File references */}
                  {service.points.length > 0 && (
                    <div className="mb-2">
                      <span className="mc-label">References</span>
                      <div className="mt-1.5 flex flex-col gap-1">
                        {service.points.map((pt, i) => (
                          <div key={i} className="flex items-center gap-2 text-[11px]">
                            <span className="font-mono text-mc-text-2 truncate flex-1">
                              {pt.file_path}
                              <span className="text-mc-text-3">:{pt.line_number}</span>
                            </span>
                            {pt.http_method && (
                              <Tag color={cfg.color} bg={cfg.bg}>
                                {pt.http_method}
                              </Tag>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Endpoints */}
                  {service.endpoints.length > 0 && (
                    <div>
                      <span className="mc-label">Endpoints</span>
                      <div className="mt-1.5 flex flex-col gap-1">
                        {service.endpoints.map((url, i) => (
                          <span key={i} className="text-[11px] font-mono text-mc-text-2 truncate">
                            {url}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Files (fallback for services_detected without points) */}
                  {service.points.length === 0 && service.files.length > 0 && (
                    <div>
                      <span className="mc-label">Files</span>
                      <div className="mt-1.5 flex flex-col gap-1">
                        {service.files.map((f, i) => (
                          <span key={i} className="text-[11px] font-mono text-mc-text-2 truncate">
                            {f}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* No results */}
      {filtered.length === 0 && search.trim() && (
        <div className="py-4 px-4 text-center text-mc-text-3 text-xs">
          No services matching "{search}"
        </div>
      )}
    </Section>
  );
}
