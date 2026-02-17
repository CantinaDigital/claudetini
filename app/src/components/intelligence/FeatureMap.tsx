import { useState, useMemo } from "react";
import type { FeatureInventory } from "../../types";
import { Tag } from "../ui/Tag";
import { Icons } from "../ui/Icons";
import { Section } from "../ui/Section";
import { SkeletonCard } from "../ui/SkeletonLoader";
import { t } from "../../styles/tokens";

interface FeatureMapProps {
  features: FeatureInventory;
  isLoading?: boolean;
  onRoadmapItemClick?: (itemText: string) => void;
}

function shortenPath(filePath: string): string {
  const parts = filePath.split("/");
  if (parts.length <= 3) return filePath;
  return `.../${parts.slice(-2).join("/")}`;
}

export function FeatureMap({ features, isLoading = false, onRoadmapItemClick }: FeatureMapProps) {
  const [search, setSearch] = useState("");
  const [activeCategory, setActiveCategory] = useState<string>("all");
  const [expandedFeature, setExpandedFeature] = useState<string | null>(null);

  const untrackedSet = useMemo(() => {
    const map = new Map<string, string>();
    for (const { feature, reason } of features.untracked_features) {
      map.set(feature.name, reason);
    }
    return map;
  }, [features.untracked_features]);

  const categories = useMemo(() => {
    const cats: Array<{ key: string; label: string; count: number }> = [
      { key: "all", label: "All", count: features.total_features },
    ];

    const sorted = Object.entries(features.by_category).sort(
      (a, b) => b[1] - a[1],
    );
    for (const [cat, count] of sorted) {
      cats.push({ key: cat, label: cat, count });
    }
    return cats;
  }, [features.by_category, features.total_features]);

  const sortedFeatures = useMemo(() => {
    let list = [...features.features];

    // Filter by category
    if (activeCategory !== "all") {
      list = list.filter((f) => f.category === activeCategory);
    }

    // Filter by search
    if (search.trim()) {
      const q = search.toLowerCase();
      list = list.filter(
        (f) =>
          f.name.toLowerCase().includes(q) ||
          f.file_path.toLowerCase().includes(q),
      );
    }

    // Sort: untracked first, then alphabetical
    return list.sort((a, b) => {
      const aTracked = !!a.roadmap_match;
      const bTracked = !!b.roadmap_match;
      if (aTracked !== bTracked) return aTracked ? 1 : -1;
      return a.name.localeCompare(b.name);
    });
  }, [features.features, activeCategory, search]);

  const trackedCount = features.features.filter((f) => f.roadmap_match).length;
  const untrackedCount = features.untracked_features.length;

  if (isLoading) {
    return (
      <Section label="Feature Map">
        <div className="p-4 flex flex-col gap-3">
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
        </div>
      </Section>
    );
  }

  if (features.total_features === 0) {
    return (
      <Section label="Feature Map">
        <div className="py-6 px-4 text-center text-mc-text-3 text-xs">
          No features detected
        </div>
      </Section>
    );
  }

  return (
    <Section label="Feature Map" right={`${features.total_features} features`}>
      {/* Stats row */}
      <div className="px-4 pt-3 pb-2 flex items-center gap-3">
        <span className="text-[10px] font-mono text-mc-text-3">
          Total <span className="font-bold text-mc-text-1">{features.total_features}</span>
        </span>
        <span className="text-[10px] font-mono text-mc-text-3">
          Tracked{" "}
          <span className="font-bold" style={{ color: t.green }}>
            {trackedCount}
          </span>
        </span>
        <span className="text-[10px] font-mono text-mc-text-3">
          Untracked{" "}
          <span className="font-bold" style={{ color: t.amber }}>
            {untrackedCount}
          </span>
        </span>
      </div>

      {/* Category filter pills */}
      <div className="px-4 pb-2 flex items-center gap-1.5 flex-wrap">
        {categories.map((cat) => {
          const isActive = activeCategory === cat.key;
          return (
            <button
              key={cat.key}
              type="button"
              onClick={() => setActiveCategory(cat.key)}
              className={`mc-tag cursor-pointer transition-colors duration-150 ${
                isActive
                  ? "bg-mc-accent-muted text-mc-accent border border-mc-accent-border"
                  : "bg-mc-surface-2 text-mc-text-3 border border-mc-border-0 hover:border-mc-border-1"
              }`}
            >
              {cat.label}
              <span className="ml-1 font-bold">{cat.count}</span>
            </button>
          );
        })}
      </div>

      {/* Search */}
      <div className="px-4 pb-2">
        <div className="relative">
          <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-mc-text-3">
            {Icons.search({ size: 11 })}
          </span>
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Filter by name or path..."
            className="w-full bg-mc-surface-2 border border-mc-border-1 rounded-lg text-xs text-mc-text-1 placeholder:text-mc-text-3 py-1.5 pl-8 pr-3 font-mono outline-none focus:border-mc-accent-border transition-colors"
          />
        </div>
      </div>

      {/* Feature list */}
      <div className="border-t border-mc-border-0">
        <div className="px-4 py-2">
          {sortedFeatures.length === 0 && (
            <div className="py-4 text-center text-mc-text-3 text-xs">
              No matching features
            </div>
          )}

          {sortedFeatures.map((feature, idx) => {
            const isTracked = !!feature.roadmap_match;
            const isExpanded = expandedFeature === `${feature.name}-${feature.file_path}`;
            const untrackedReason = untrackedSet.get(feature.name);
            const importCount = features.import_counts[feature.name] ?? feature.import_count ?? 0;
            const isHighCoupling = importCount > 5;

            return (
              <div
                key={`${feature.name}-${feature.file_path}`}
                style={{ "--stagger-delay": `${idx * 0.015}s` } as React.CSSProperties}
                className={`py-2.5 animate-slide-up [animation-delay:var(--stagger-delay)] [animation-fill-mode:both] ${
                  idx < sortedFeatures.length - 1 ? "border-b border-mc-border-0" : ""
                }`}
              >
                <div
                  className={`flex items-center gap-2.5 ${!isTracked ? "cursor-pointer" : ""}`}
                  onClick={() => {
                    if (!isTracked) {
                      setExpandedFeature(
                        isExpanded ? null : `${feature.name}-${feature.file_path}`,
                      );
                    }
                  }}
                >
                  {/* Tracking dot */}
                  <span
                    className="w-2 h-2 rounded-full flex-shrink-0"
                    style={{ backgroundColor: isTracked ? t.green : t.amber }}
                    title={isTracked ? "Tracked in roadmap" : "Untracked"}
                  />

                  {/* Name */}
                  <span className="text-xs font-semibold text-mc-text-0 truncate min-w-0 flex-1">
                    {feature.name}
                  </span>

                  {/* Import count */}
                  {importCount > 0 && (
                    <span
                      className={`text-[10px] font-mono flex-shrink-0 ${
                        isHighCoupling ? "font-bold" : ""
                      }`}
                      style={{ color: isHighCoupling ? t.amber : t.text3 }}
                      title={`${importCount} imports`}
                    >
                      {importCount}
                    </span>
                  )}

                  {/* High coupling badge */}
                  {isHighCoupling && (
                    <Tag color={t.amber} bg={t.amberMuted}>
                      High coupling
                    </Tag>
                  )}

                  {/* Category tag */}
                  <Tag>{feature.category}</Tag>

                  {/* File path */}
                  <span className="text-[10px] font-mono text-mc-text-3 truncate flex-shrink-0 max-w-[140px]">
                    {shortenPath(feature.file_path)}
                  </span>

                  {/* Roadmap link */}
                  {isTracked && feature.roadmap_match && onRoadmapItemClick && (
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        onRoadmapItemClick(feature.roadmap_match!);
                      }}
                      className="text-[10px] font-mono text-mc-accent hover:text-mc-text-0 cursor-pointer transition-colors flex-shrink-0"
                      title={feature.roadmap_match}
                    >
                      Roadmap
                    </button>
                  )}

                  {/* Expand indicator for untracked */}
                  {!isTracked && untrackedReason && (
                    <span className="flex-shrink-0 text-mc-text-3">
                      {Icons.chevDown({ size: 9, open: isExpanded })}
                    </span>
                  )}
                </div>

                {/* Expanded reason */}
                {isExpanded && untrackedReason && (
                  <div className="mt-2 ml-4.5 pl-2.5 border-l-2 border-mc-amber-border animate-fade-in">
                    <span className="text-[11px] text-mc-text-3 leading-relaxed">
                      {untrackedReason}
                    </span>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </Section>
  );
}
