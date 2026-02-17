# Unified Project Plan

## Milestone 1: Project Picker Foundation
- [x] **1.1** Create `ProjectPickerView.tsx` — Full-screen project selection component
- [x] **1.2** Implement "Add Project" folder picker using Tauri's native dialog
- [x] **1.3** Add "Scan for Projects" to auto-discover Claude projects in common locations
- [x] **1.4** Display recently opened projects with last-opened timestamps
- [x] **1.5** Show project health preview badges in picker list
- [x] **1.6** Add "Remove from list" context action (doesn't delete files)
- [x] **1.7** Persist selected project to app state and registry
- [x] **1.8** Add keyboard navigation (arrow keys, Enter to select)

## Milestone 2: Readiness Scorecard Engine
- [x] **2.1** Define `ReadinessCheck` interface with name, category, status, weight, remediation
- [x] **2.2** Implement `ReadinessScanner` class with all check methods
- [x] **2.3** Check: Git repository (is valid repo, has remote, clean state)
- [x] **2.4** Check: README.md (exists, >500 chars, has sections)
- [x] **2.5** Check: CLAUDE.md (exists, >200 chars, has conventions section)
- [x] **2.6** Check: Planning directory (.planning/ or .claude/planning/)
- [x] **2.7** Check: ROADMAP.md (exists, has milestones, not stale)
- [x] **2.8** Check: docs/ directory (exists, has architecture or similar)
- [x] **2.9** Check: agents/ directory (for projects using sub-agents)
- [x] **2.10** Check: .gitignore (exists, excludes common patterns)
- [x] **2.11** Check: Tests directory (tests/, __tests__, spec/)
- [x] **2.12** Check: CI/CD config (.github/workflows/, .gitlab-ci.yml)
- [x] **2.13** Check: Security (no secrets in committed files)
- [x] **2.14** Check: Dependencies lock file (package-lock.json, poetry.lock, etc.)
- [x] **2.15** Compute weighted readiness score (0-100)
- [x] **2.16** Create `/api/project/readiness/{project_id}` endpoint

## Milestone 3: Scorecard UI
- [x] **3.1** Create `ScorecardView.tsx` — Full readiness visualization
- [x] **3.2** Display overall score with progress ring (0-100)
- [x] **3.3** Group checks by category (Essential, Recommended, Optional)
- [x] **3.4** Show status icons per check (pass, warn, fail, skip)
- [x] **3.5** Display remediation hint for each failed check
- [x] **3.6** Add "Bootstrap Missing Items" primary CTA button
- [x] **3.7** Add "Skip for Now" secondary action
- [x] **3.8** Add "Re-scan" refresh button
- [x] **3.9** Show diff between last scan and current (if returning)

## Milestone 4: Bootstrap Engine
- [x] **4.1** Create `BootstrapEngine` class with artifact generators
- [x] **4.2** Create `bootstrap_prompts/` directory with prompt templates
- [x] **4.3** Prompt: Generate CLAUDE.md from codebase analysis
- [x] **4.4** Prompt: Generate ROADMAP.md with initial milestones
- [x] **4.5** Prompt: Generate docs/ARCHITECTURE.md
- [x] **4.6** Prompt: Generate basic .gitignore
- [x] **4.7** Prompt: Create agents/ folder with starter templates
- [x] **4.8** Prompt: Analyze and document existing code structure
- [x] **4.9** Create `BootstrapRunner` to execute prompts sequentially
- [x] **4.10** Add progress tracking for multi-step bootstrap
- [x] **4.11** Handle partial failures gracefully (continue others)
- [x] **4.12** Create `/api/project/bootstrap/{project_id}` endpoint
- [x] **4.13** Add WebSocket or SSE for real-time bootstrap progress

## Milestone 5: Bootstrap UI
- [x] **5.1** Create `BootstrapProgressView.tsx` component
- [ ] **5.2** Show checklist of items being created
- [x] **5.3** Real-time status updates (pending, running, complete, failed)
- [x] **5.4** Display Claude's output in expandable sections
- [ ] **5.5** Add "Pause" and "Cancel" controls
- [x] **5.6** Show estimated cost before starting
- [x] **5.7** On completion, show summary and "Continue to Dashboard" CTA
- [x] **5.8** Handle errors with "Retry" or "Skip" options

## Milestone 6: App State Machine
- [x] **6.1** Define `AppScreen` enum: picker | scorecard | bootstrap | dashboard
- [ ] **6.2** Create `AppStateManager` with screen transitions
- [x] **6.3** Add route guard: picker → scorecard (always runs on new project)
- [x] **6.4** Add route guard: scorecard → bootstrap (if user clicks bootstrap)
- [x] **6.5** Add route guard: scorecard → dashboard (if skip or score >= 70)
- [x] **6.6** Add "Switch Project" action from dashboard header
- [x] **6.7** Persist last screen state for session resume
- [ ] **6.8** Add breadcrumb navigation for orientation

## Milestone 7: Multi-Project Management
- [x] **7.1** Add project dropdown in dashboard header
- [x] **7.2** Show mini-health badge per project in dropdown
- [ ] **7.3** "Open in New Window" action (Tauri multi-window)
- [x] **7.4** Project search/filter in picker
- [x] **7.5** Sort options: name, last opened, health score, recent activity
- [x] **7.6** Bulk actions: remove multiple, re-scan all

## Milestone 8: Project Auto-Discovery
- [x] **8.1** Scan `~/.claude/projects/` for project hashes
- [x] **8.2** Reverse-lookup project paths from session JSONL files
- [ ] **8.3** Scan common locations (~/Documents, ~/Projects, ~/Code, ~/dev)
- [x] **8.4** Detect Git repos with `.claude/` or `CLAUDE.md`
- [x] **8.5** Present discovered projects with "Add to Claudetini" action
- [ ] **8.6** Exclude already-registered projects from discovery results
- [ ] **8.7** Background scanning with progress indicator

## Milestone 9: Wizard Polish
- [x] **9.1** Add animations/transitions between wizard steps
- [x] **9.2** Welcome screen for first-time users
- [x] **9.3** Tooltips explaining each readiness check
- [x] **9.4** "What is this?" help links throughout
- [x] **9.5** Dark mode throughout (consistent with dashboard)
- [x] **9.6** Keyboard shortcuts for all actions
- [x] **9.7** Accessibility audit (screen reader, focus management)

## Milestone 10: Packaging & Distribution
- [x] **10.1** Configure Tauri for macOS .dmg / .app bundle
- [x] **10.2** Configure Tauri for Windows .exe / .msi installer
- [x] **10.3** Configure Tauri for Linux .AppImage / .deb
- [x] **10.4** Auto-start Python sidecar on app launch
- [x] **10.5** Bundle Python runtime or use pyinstaller for sidecar
- [ ] **10.6** Code signing for macOS (notarization)
- [ ] **10.7** Code signing for Windows (Authenticode)
- [ ] **10.8** Auto-update mechanism (Tauri updater)
- [ ] **10.9** First public release workflow (GitHub Releases)

## Milestone 11: Design System Consolidation
- [x] **11.1** Audit all components for inline `style={{}}` usage
- [ ] **11.2** Extend `tokens.ts` with spacing, radii, and shadow tokens
- [x] **11.3** Add CSS custom properties in `global.css` from token values
- [x] **11.4** Add reusable utility classes in `@layer components`
- [x] **11.5** Replace inline styles with Tailwind classes across all components
- [ ] **11.6** Ensure single-column tabs have sections at 100% container width
- [ ] **11.7** Remove max-width constraints preventing full-width layouts
- [x] **11.8** Use consistent container/section patterns across all tabs

## Milestone 12: Task Dispatch UX Overhaul (CRITICAL)
- [x] **12.1** Create `PromptEnricher` to build context-aware prompts with file hints, patterns, acceptance criteria
- [x] **12.2** Add codebase context injection: relevant files, component structure, design patterns from CLAUDE.md
- [x] **12.3** Stream real Claude Code CLI output to UI (tail the output file created by dispatcher.py)
- [x] **12.4** Replace fake "Waiting for Claude Code..." messages with actual CLI output
- [x] **12.5** Show thinking/tool-use/file-edit events as they happen (parse JSONL or text output)
- [x] **12.6** Add post-dispatch summary: files changed, lines added/removed, git diff preview
- [x] **12.7** Implement auto-reconciliation: analyze git changes and offer to mark task complete
- [x] **12.8** Add "What was accomplished?" summary generation using Claude Code analysis
- [ ] **12.9** Show success/failure state clearly with next actions (commit, review, iterate)
- [x] **12.10** Add "Review Changes" button that opens git diff view
- [x] **12.11** Add "Mark Task Complete" action when reconciliation confirms success
- [x] **12.12** Fix progress indicators to reflect real Claude Code state, not elapsed time
- [x] **12.13** Add test coverage for prompt enrichment and output parsing

## Milestone 13: Project Intelligence Tab
- [x] **13.1** Create `hardcoded_scanner.py` — Detect hardcoded URLs, IPs, TODO/FIXME markers, placeholder data (lorem ipsum, test@example.com, foo/bar/baz, nil UUIDs), magic numbers, and absolute file paths in source code. Follow `secrets_scanner.py` pattern: `HardcodedScanner(project_path)` class with `scan() -> HardcodedScanResult`. Include `HardcodedFinding` dataclass with `file_path`, `line_number`, `category`, `severity`, `matched_text`, `suggestion`. Categories: `url`, `ip_address`, `port`, `todo_marker`, `placeholder`, `absolute_path`, `magic_number`. Severity logic: placeholder in production path (src/, lib/, app/) = critical; in test path = info; TODOs = warning. Reuse `SCANNABLE_EXTENSIONS` and `SKIP_DIRECTORIES` sets (duplicate from secrets_scanner, don't import).
- [x] **13.2** Add environment config audit to `hardcoded_scanner.py` — Scan for `process.env.X` and `os.environ["X"]` references in code, cross-reference against `.env.example` file. Flag env vars referenced in code but not documented in `.env.example`. Add `env_reference` category to findings.
- [x] **13.3** Add documentation drift detection to `hardcoded_scanner.py` — Scan README.md and CLAUDE.md for file paths, command references, and function names that no longer exist in the codebase. Add `doc_drift` category to findings.
- [x] **13.4** Create `integration_scanner.py` — Discover external service integrations and internal API routes. `IntegrationScanner(project_path)` with `scan() -> IntegrationReport`. Detect HTTP client usage (requests, fetch, axios, httpx, aiohttp, got, ky), extract API endpoint URLs from string literals, identify known services (Stripe, AWS, Firebase, Supabase, Twilio, SendGrid, OpenAI, Anthropic, Slack, Sentry, Datadog — 20+ URL patterns), detect SDK imports (import stripe, import boto3, etc.), and map internal route definitions (FastAPI @router, Express app.get, Flask @app.route, Django path()). Models: `IntegrationPoint(service_name, integration_type, file_path, line_number, matched_text, endpoint_url, http_method)`, `ServiceSummary(service_name, count, endpoints, files)`, `IntegrationReport(integrations, services_detected, files_scanned)`. Integration types: `external_api`, `internal_route`, `sdk_import`, `database`.
- [x] **13.5** Create `freshness_analyzer.py` — Analyze code staleness using git history. `FreshnessAnalyzer(project_path)` with `analyze() -> FreshnessReport`. Use batch git command (`git log --all --format="%H|%aI|%an" --name-only`) to build per-file map in O(1) git calls. Models: `FileFreshness(file_path, last_modified, days_since_modified, commit_count, category, last_author)`, `AgeDistribution(fresh/aging/stale/abandoned counts)`, `FreshnessReport(files, age_distribution, stale_files, abandoned_files, single_commit_files, freshness_score)`. Categories: fresh (<30d), aging (30-90d), stale (90-365d), abandoned (>365d). Use `GitRepo` from `src/core/git_utils.py`.
- [x] **13.6** Add migration tracker to `freshness_analyzer.py` — Detect partial migrations by scanning for mixed code patterns. Detect: React class vs functional components, var vs let/const, %-formatting vs f-strings, require() vs import. For each pattern pair, count files using old vs new pattern. If >20% use old and >20% use new, flag as "partial migration". Add `DeprecatedPatternMatch(file_path, line_number, pattern_name, matched_text, replacement)` and `partial_migrations` list to `FreshnessReport`.
- [x] **13.7** Create `dependency_analyzer.py` — Analyze dependency health across ecosystems. `DependencyAnalyzer(project_path)` with `analyze() -> DependencyReport`. Auto-detect ecosystems by checking for manifest files (package.json, pyproject.toml, requirements.txt, Cargo.toml, go.mod). For npm: parse package.json, run `npm outdated --json`, run `npm audit --json`. For pip: parse manifests, run `pip list --outdated --format=json`, optionally `pip-audit --format=json`. For cargo/go: manifest parsing only. Models: `DependencyInfo(name, current_version, latest_version, update_severity, ecosystem, is_dev)`, `VulnerabilityInfo(package_name, severity, advisory_id, title, fixed_in)`, `EcosystemReport(ecosystem, manifest_path, outdated, vulnerabilities)`, `DependencyReport(ecosystems, health_score)`. Semver comparison for major/minor/patch. Health score: start 100, -5 per major outdated, -1 per minor, -15 per critical vuln, -3 per other vuln. All subprocess calls use timeout=60, catch TimeoutExpired and FileNotFoundError gracefully.
- [x] **13.8** Create `feature_inventory.py` — Map project features and cross-reference with roadmap. `FeatureInventoryScanner(project_path, roadmap=None)` with `scan() -> FeatureInventory`. Detect React components (`export function/const PascalCase`), hooks (`use*`), FastAPI/Express/Flask/Django routes, Pydantic models, dataclasses, service/manager/handler/controller classes, CLI commands. Models: `DetectedFeature(name, category, file_path, line_number, framework, loc, is_exported)`, `FeatureMapping(feature, roadmap_item_text, confidence, matched_keywords)`, `UntrackedFeature(feature, reason)`, `FeatureInventory(features, by_category, roadmap_mappings, untracked_features, total_features)`. Cross-reference with roadmap using keyword extraction (duplicate `_extract_keywords()` from `reconciliation.py`). Features with loc >= 50 and no roadmap match at confidence >= 0.3 are flagged as untracked.
- [x] **13.9** Add coupling analysis to `feature_inventory.py` — Count how many files import each module. For each detected feature/module, track `import_count` (number of other files that import it). Rank modules by dependents count. Add `most_coupled` and `import_counts` to `FeatureInventory`.
- [x] **13.10** Create `intelligence.py` orchestrator — `ProjectIntelligence(project_path)` that runs all 5 scanners and produces a unified `IntelligenceReport`. Models: `IntelligenceSummary(total/critical/warning/info counts)`, `IntelligenceReport(project_path, generated_at, overall_score, grade, hardcoded, dependencies, integrations, freshness, features, summary, top_issues, scan_duration_ms, scans_completed, scans_failed)`. Methods: `run_full_scan()`, `run_scanner(name)`, `get_cached_report()`. Score weights: hardcoded=0.20, dependencies=0.25, integrations=0.10, freshness=0.25, features=0.20. Grades: A(>=90), B(>=75), C(>=60), D(>=40), F(<40). Each scanner wrapped in try/except for error isolation. Cache results using `JsonCache` from `src/core/cache.py` at `~/.claudetini/projects/{hash}/intelligence-cache.json`. Top issues: prioritize critical vulns > hardcoded critical > stale files > outdated deps > untracked features.
- [x] **13.11** Create `app/python-sidecar/sidecar/api/routes/intelligence.py` — FastAPI router with prefix `/intelligence`. Pydantic response models for each scanner section + combined `IntelligenceReportResponse` with `CategoryScore` summaries. Endpoints: `POST /api/intelligence/scan` (full scan, body: `{project_path}`, timeout 120s), `GET /api/intelligence/{project_path:path}` (cached report), `GET /api/intelligence/summary/{project_path:path}` (lightweight: score + categories + staleness flag), `POST /api/intelligence/scan/{scanner_name}` (individual scanner). Follow `readiness.py` pattern for structure. Register in `server.py` with `app.include_router(intelligence.router, prefix="/api", tags=["intelligence"])`.
- [x] **13.12** Add TypeScript types to `app/src/types/index.ts` — Add interfaces: `HardcodedFinding`, `HardcodedScanResult`, `DependencyPackage`, `DependencyReport`, `IntegrationPoint`, `IntegrationMap`, `FileFreshness`, `FreshnessReport`, `FeatureEntry`, `FeatureInventory`, `CategoryScore`, `IntelligenceReport`, `IntelligenceSummary`. All fields match the Pydantic response models from 13.11.
- [x] **13.13** Add API client functions to `app/src/api/backend.ts` — Add to the `api` object: `scanIntelligence(projectPath)` (POST, 120s timeout), `getIntelligence(projectPath)` (GET), `getIntelligenceSummary(projectPath)` (GET, 5s timeout), `scanIntelligenceSingle(projectPath, scannerName)` (POST, 60s timeout). Import new types from types/index.ts.
- [x] **13.14** Create `app/src/components/intelligence/CollapsibleSection.tsx` — Reusable collapsible wrapper with title, icon, subtitle, optional badge ReactNode, defaultOpen prop, chevron toggle animation. Uses `bg-mc-surface-1`, `border-mc-border-0`, `rounded-xl`. Clicking header toggles content visibility.
- [x] **13.15** Create `app/src/components/intelligence/SummaryBar.tsx` — Score ring (reuse `ReadinessRing` with new optional `label` prop), category severity pills showing scanner name + status + finding count, scan timestamp with relative time, "Scan Now" button with loading state. Modify `ReadinessRing.tsx` to accept optional `label?: string` prop (default "Readiness Score").
- [x] **13.16** Create `app/src/components/intelligence/TechDebtHeatmap.tsx` — Combine hardcoded findings + freshness data per-file into a heat score. Formula: issues(60%) + staleness(40%). Show files as rows sorted by heat score descending (top 50). Color bars: red (>=70), amber (>=40), green (<40). Click to expand showing specific findings per file with line numbers, categories, and matched text.
- [x] **13.17** Create `app/src/components/intelligence/HardcodedFindings.tsx` — Findings grouped by severity (critical, warning, info). Filter pills (all/critical/warning/info) with counts. Search input filtering by file path, matched text, or category. Each finding shows file:line, matched text (truncated), category tag. Uses `SeverityTag` component.
- [x] **13.18** Create `app/src/components/intelligence/DependencyHealth.tsx` — Package cards in 2-column grid. Filter: all/outdated/vulnerable with counts. Each card shows package name, current -> latest version, severity badge, package manager label. Vulnerable packages highlighted with red border/background. Vulnerability detail shown when present.
- [x] **13.19** Create `app/src/components/intelligence/IntegrationsMap.tsx` — Service cards in 3-column grid with type icons. Click to expand showing file references with line numbers and endpoint URLs. Uses `Tag` component for integration type labels.
- [x] **13.20** Create `app/src/components/intelligence/CodeFreshness.tsx` — Stats row (total files, stale count, abandoned count, median age). Horizontal bar chart for age distribution buckets. Stale files list sorted by age (descending) with last author and days-old count. Abandoned files highlighted in red, stale in amber.
- [x] **13.21** Create `app/src/components/intelligence/FeatureMap.tsx` — Category filter pills (all, component, route, hook, model, etc.) with counts. Tracked/untracked stats display. Feature list with green dot (tracked) or amber dot (untracked), name, category tag, file path, and roadmap item link if tracked. Sort: untracked first, then alphabetical.
- [x] **13.22** Create `app/src/components/intelligence/IntelligenceTab.tsx` — Main tab orchestrator. On mount: check frontend cache, then backend cache (parallel `getIntelligenceSummary` + `getIntelligence`). Show skeleton loaders while loading. If no data, show "Run a scan" prompt. "Scan Now" triggers `scanIntelligence()`. Renders SummaryBar + 6 CollapsibleSections (Tech Debt Heatmap, Hardcoded Values, Dependency Health, Integrations & APIs, Code Freshness, Feature Map). Max width 900px. Error display for failed scans.
- [x] **13.23** Register Intelligence tab in `app/src/App.tsx` — Add "Intelligence" to TABS array at index 4 (between Quality Gates and Logs). Import `IntelligenceTab`. Add render block with `TabErrorBoundary`. Renumber Logs to index 5 and Settings to index 6. Update `handleNavigateToSettings` to use `setActiveTab(6)`. Verify all `setActiveTab` calls reference correct indexes.

## Success Criteria
- [x] User can install Claudetini to Applications folder
- [x] User can open any folder as a Claude project
- [x] Scorecard accurately assesses project readiness
- [x] Bootstrap creates functional CLAUDE.md and ROADMAP.md
- [x] User can reach dashboard with 100% readiness score
- [x] Multiple projects can be managed from one app instance
- [x] App auto-discovers existing Claude Code projects
- [ ] Intelligence tab scans and reports hardcoded values, dependency health, integrations, code freshness, and feature coverage
- [ ] Each scanner produces actionable findings with severity levels and suggested fixes
- [ ] Overall intelligence score accurately reflects project health across all 5 dimensions
- [ ] Cached results load instantly; stale indicator shows when data is outdated
- [ ] Environment config audit catches undocumented env vars
- [ ] Documentation drift detection catches dead references in README/CLAUDE.md
- [ ] Migration tracker identifies partial codebase migrations
- [ ] Coupling analysis ranks modules by import dependents
