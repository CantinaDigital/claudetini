"""Feature inventory scanner with roadmap cross-referencing and coupling analysis.

Detects features across multiple frameworks (React, FastAPI, Flask, Django, Express,
Pydantic, Click/Typer, etc.), maps them to roadmap items, and identifies the most
coupled modules by import count.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

from .roadmap import Roadmap


@dataclass(frozen=True)
class DetectedFeature:
    """A feature detected in the codebase."""

    name: str
    category: str
    file_path: str
    line_number: int
    framework: str
    loc: int
    is_exported: bool


@dataclass(frozen=True)
class FeatureMapping:
    """A mapping between a detected feature and a roadmap item."""

    feature: DetectedFeature
    roadmap_item_text: str
    confidence: float  # 0.0 to 1.0
    matched_keywords: tuple[str, ...]


@dataclass(frozen=True)
class UntrackedFeature:
    """A feature not matched to any roadmap item."""

    feature: DetectedFeature
    reason: str


@dataclass
class FeatureInventory:
    """Complete feature inventory with categorisation, roadmap mapping, and coupling."""

    features: list[DetectedFeature] = field(default_factory=list)
    by_category: dict[str, list[DetectedFeature]] = field(default_factory=dict)
    roadmap_mappings: dict[str, list[FeatureMapping]] = field(default_factory=dict)
    untracked_features: list[UntrackedFeature] = field(default_factory=list)
    total_features: int = 0
    most_coupled: list[dict] = field(default_factory=list)
    import_counts: dict[str, int] = field(default_factory=dict)


# ── Detection patterns ──────────────────────────────────────────────

# React components: export function/const PascalCase
_REACT_EXPORT_FUNC = re.compile(
    r"^export\s+(?:default\s+)?function\s+([A-Z][a-zA-Z0-9]+)",
    re.MULTILINE,
)
_REACT_EXPORT_CONST = re.compile(
    r"^export\s+(?:default\s+)?const\s+([A-Z][a-zA-Z0-9]+)\s*[=:]",
    re.MULTILINE,
)

# Hooks: export function useXxx
_REACT_HOOK = re.compile(
    r"^export\s+(?:default\s+)?(?:function|const)\s+(use[A-Z][a-zA-Z0-9]*)",
    re.MULTILINE,
)

# FastAPI routes: @router.get / @router.post / @app.get etc.
_FASTAPI_ROUTE = re.compile(
    r"^@(?:router|app)\.(get|post|put|patch|delete)\s*\(\s*['\"]([^'\"]+)['\"]",
    re.MULTILINE,
)
_FASTAPI_FUNC = re.compile(
    r"^(?:async\s+)?def\s+(\w+)",
    re.MULTILINE,
)

# Express routes: app.get / router.get etc.
_EXPRESS_ROUTE = re.compile(
    r"(?:app|router)\.(get|post|put|patch|delete)\s*\(\s*['\"]([^'\"]+)['\"]",
    re.MULTILINE,
)

# Flask routes: @app.route
_FLASK_ROUTE = re.compile(
    r"^@(?:app|blueprint|bp)\.\s*route\s*\(\s*['\"]([^'\"]+)['\"]",
    re.MULTILINE,
)
_FLASK_FUNC = re.compile(
    r"^def\s+(\w+)",
    re.MULTILINE,
)

# Django url patterns: path('...',
_DJANGO_PATH = re.compile(
    r"path\s*\(\s*['\"]([^'\"]*)['\"]",
    re.MULTILINE,
)

# Pydantic models: class X(BaseModel)
_PYDANTIC_MODEL = re.compile(
    r"^class\s+(\w+)\s*\(.*?BaseModel.*?\)\s*:",
    re.MULTILINE,
)

# Dataclasses: @dataclass class X
_DATACLASS = re.compile(
    r"^@dataclass(?:\(.*?\))?\s*\nclass\s+(\w+)",
    re.MULTILINE,
)

# Service/manager/handler/controller classes
_SERVICE_CLASS = re.compile(
    r"^class\s+(\w+(?:Service|Manager|Handler|Controller))\s*[\(:]",
    re.MULTILINE,
)

# CLI commands: Click @click.command, Typer @app.command
_CLICK_COMMAND = re.compile(
    r"^@(?:click\.command|click\.group|cli\.command|cli\.group)\s*\(",
    re.MULTILINE,
)
_TYPER_COMMAND = re.compile(
    r"^@(?:app|typer_app)\.command\s*\(",
    re.MULTILINE,
)
_CLI_FUNC = re.compile(
    r"^def\s+(\w+)",
    re.MULTILINE,
)

# Import patterns for coupling analysis
_PYTHON_IMPORT = re.compile(
    r"^(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))",
    re.MULTILINE,
)
_TS_IMPORT = re.compile(
    r"""(?:import\s+.*?from\s+['\"]([^'\"]+)['\"]|require\s*\(\s*['\"]([^'\"]+)['\"]\s*\))""",
    re.MULTILINE,
)

# File extensions by ecosystem
_CODE_EXTENSIONS: dict[str, list[str]] = {
    "typescript": [".ts", ".tsx", ".jsx"],
    "python": [".py"],
    "javascript": [".js", ".mjs"],
}

# Ignored directories
_IGNORED_DIRS = {
    "node_modules", ".git", "__pycache__", ".venv", "venv",
    "dist", "build", ".next", ".nuxt", "target",
    ".tox", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "egg-info",
}


class FeatureInventoryScanner:
    """Scan a project to detect features, map to roadmap, and analyse coupling."""

    def __init__(self, project_path: Path, roadmap: Roadmap | None = None):
        self.project_path = project_path.resolve()
        self.roadmap = roadmap

    def scan(self) -> FeatureInventory:
        """Scan the project and produce a full feature inventory.

        Returns:
            FeatureInventory with detected features, categories, roadmap mappings,
            untracked features, and coupling analysis.
        """
        features = self._detect_all_features()

        # Group by category
        by_category: dict[str, list[DetectedFeature]] = {}
        for feat in features:
            by_category.setdefault(feat.category, []).append(feat)

        # Roadmap cross-reference
        roadmap_mappings: dict[str, list[FeatureMapping]] = {}
        untracked: list[UntrackedFeature] = []
        if self.roadmap:
            roadmap_mappings, untracked = self._cross_reference_roadmap(features)

        # Coupling analysis
        import_counts, most_coupled = self._analyze_coupling(features)

        return FeatureInventory(
            features=features,
            by_category=by_category,
            roadmap_mappings=roadmap_mappings,
            untracked_features=untracked,
            total_features=len(features),
            most_coupled=most_coupled,
            import_counts=import_counts,
        )

    # ── Feature Detection ───────────────────────────────────────────

    def _detect_all_features(self) -> list[DetectedFeature]:
        """Walk the project tree and detect features in all code files."""
        features: list[DetectedFeature] = []

        for file_path in self._iter_code_files():
            try:
                content = file_path.read_text(errors="ignore")
            except OSError:
                continue

            rel_path = str(file_path.relative_to(self.project_path))
            lines = content.splitlines()
            total_lines = len(lines)
            ext = file_path.suffix.lower()

            if ext in (".ts", ".tsx", ".jsx", ".js", ".mjs"):
                features.extend(self._detect_react_components(content, rel_path, total_lines))
                features.extend(self._detect_hooks(content, rel_path, total_lines))
                features.extend(self._detect_express_routes(content, rel_path, total_lines))
            elif ext == ".py":
                features.extend(self._detect_fastapi_routes(content, rel_path, total_lines))
                features.extend(self._detect_flask_routes(content, rel_path, total_lines))
                features.extend(self._detect_django_paths(content, rel_path, total_lines))
                features.extend(self._detect_pydantic_models(content, rel_path, total_lines))
                features.extend(self._detect_dataclasses(content, rel_path, total_lines))
                features.extend(self._detect_service_classes(content, rel_path, total_lines))
                features.extend(self._detect_cli_commands(content, rel_path, total_lines))

        return features

    def _detect_react_components(
        self, content: str, rel_path: str, total_lines: int
    ) -> list[DetectedFeature]:
        """Detect exported React components."""
        features: list[DetectedFeature] = []
        seen: set[str] = set()

        for pattern in (_REACT_EXPORT_FUNC, _REACT_EXPORT_CONST):
            for match in pattern.finditer(content):
                name = match.group(1)
                # Skip hooks (handled separately)
                if name.startswith("use"):
                    continue
                if name in seen:
                    continue
                seen.add(name)
                line_number = content[:match.start()].count("\n") + 1
                loc = self._estimate_feature_loc(content, match.start(), total_lines)
                features.append(
                    DetectedFeature(
                        name=name,
                        category="component",
                        file_path=rel_path,
                        line_number=line_number,
                        framework="react",
                        loc=loc,
                        is_exported=True,
                    )
                )

        return features

    def _detect_hooks(
        self, content: str, rel_path: str, total_lines: int
    ) -> list[DetectedFeature]:
        """Detect exported React hooks."""
        features: list[DetectedFeature] = []

        for match in _REACT_HOOK.finditer(content):
            name = match.group(1)
            line_number = content[:match.start()].count("\n") + 1
            loc = self._estimate_feature_loc(content, match.start(), total_lines)
            features.append(
                DetectedFeature(
                    name=name,
                    category="hook",
                    file_path=rel_path,
                    line_number=line_number,
                    framework="react",
                    loc=loc,
                    is_exported=True,
                )
            )

        return features

    def _detect_express_routes(
        self, content: str, rel_path: str, total_lines: int
    ) -> list[DetectedFeature]:
        """Detect Express.js route definitions."""
        features: list[DetectedFeature] = []

        for match in _EXPRESS_ROUTE.finditer(content):
            method = match.group(1).upper()
            route_path = match.group(2)
            name = f"{method} {route_path}"
            line_number = content[:match.start()].count("\n") + 1
            loc = self._estimate_feature_loc(content, match.start(), total_lines)
            features.append(
                DetectedFeature(
                    name=name,
                    category="route",
                    file_path=rel_path,
                    line_number=line_number,
                    framework="express",
                    loc=loc,
                    is_exported=False,
                )
            )

        return features

    def _detect_fastapi_routes(
        self, content: str, rel_path: str, total_lines: int
    ) -> list[DetectedFeature]:
        """Detect FastAPI route definitions."""
        features: list[DetectedFeature] = []

        for match in _FASTAPI_ROUTE.finditer(content):
            method = match.group(1).upper()
            route_path = match.group(2)
            # Find the function name on the next line(s)
            after = content[match.end():]
            func_match = _FASTAPI_FUNC.search(after)
            func_name = func_match.group(1) if func_match else "unknown"
            name = f"{method} {route_path} ({func_name})"
            line_number = content[:match.start()].count("\n") + 1
            loc = self._estimate_feature_loc(content, match.start(), total_lines)
            features.append(
                DetectedFeature(
                    name=name,
                    category="route",
                    file_path=rel_path,
                    line_number=line_number,
                    framework="fastapi",
                    loc=loc,
                    is_exported=False,
                )
            )

        return features

    def _detect_flask_routes(
        self, content: str, rel_path: str, total_lines: int
    ) -> list[DetectedFeature]:
        """Detect Flask route definitions."""
        features: list[DetectedFeature] = []

        for match in _FLASK_ROUTE.finditer(content):
            route_path = match.group(1)
            after = content[match.end():]
            func_match = _FLASK_FUNC.search(after)
            func_name = func_match.group(1) if func_match else "unknown"
            name = f"{route_path} ({func_name})"
            line_number = content[:match.start()].count("\n") + 1
            loc = self._estimate_feature_loc(content, match.start(), total_lines)
            features.append(
                DetectedFeature(
                    name=name,
                    category="route",
                    file_path=rel_path,
                    line_number=line_number,
                    framework="flask",
                    loc=loc,
                    is_exported=False,
                )
            )

        return features

    def _detect_django_paths(
        self, content: str, rel_path: str, total_lines: int
    ) -> list[DetectedFeature]:
        """Detect Django URL path() definitions."""
        features: list[DetectedFeature] = []

        for match in _DJANGO_PATH.finditer(content):
            route_path = match.group(1) or "/"
            name = f"path({route_path!r})"
            line_number = content[:match.start()].count("\n") + 1
            loc = self._estimate_feature_loc(content, match.start(), total_lines)
            features.append(
                DetectedFeature(
                    name=name,
                    category="route",
                    file_path=rel_path,
                    line_number=line_number,
                    framework="django",
                    loc=loc,
                    is_exported=False,
                )
            )

        return features

    def _detect_pydantic_models(
        self, content: str, rel_path: str, total_lines: int
    ) -> list[DetectedFeature]:
        """Detect Pydantic BaseModel subclasses."""
        features: list[DetectedFeature] = []

        for match in _PYDANTIC_MODEL.finditer(content):
            name = match.group(1)
            line_number = content[:match.start()].count("\n") + 1
            loc = self._estimate_feature_loc(content, match.start(), total_lines)
            features.append(
                DetectedFeature(
                    name=name,
                    category="model",
                    file_path=rel_path,
                    line_number=line_number,
                    framework="pydantic",
                    loc=loc,
                    is_exported=True,
                )
            )

        return features

    def _detect_dataclasses(
        self, content: str, rel_path: str, total_lines: int
    ) -> list[DetectedFeature]:
        """Detect @dataclass classes."""
        features: list[DetectedFeature] = []

        for match in _DATACLASS.finditer(content):
            name = match.group(1)
            line_number = content[:match.start()].count("\n") + 1
            loc = self._estimate_feature_loc(content, match.start(), total_lines)
            features.append(
                DetectedFeature(
                    name=name,
                    category="model",
                    file_path=rel_path,
                    line_number=line_number,
                    framework="dataclass",
                    loc=loc,
                    is_exported=True,
                )
            )

        return features

    def _detect_service_classes(
        self, content: str, rel_path: str, total_lines: int
    ) -> list[DetectedFeature]:
        """Detect Service/Manager/Handler/Controller classes."""
        features: list[DetectedFeature] = []

        for match in _SERVICE_CLASS.finditer(content):
            name = match.group(1)
            line_number = content[:match.start()].count("\n") + 1
            loc = self._estimate_feature_loc(content, match.start(), total_lines)
            # Determine category from suffix
            name_lower = name.lower()
            if name_lower.endswith("controller"):
                category = "controller"
            elif name_lower.endswith("handler"):
                category = "handler"
            elif name_lower.endswith("manager"):
                category = "manager"
            else:
                category = "service"
            features.append(
                DetectedFeature(
                    name=name,
                    category=category,
                    file_path=rel_path,
                    line_number=line_number,
                    framework="python",
                    loc=loc,
                    is_exported=True,
                )
            )

        return features

    def _detect_cli_commands(
        self, content: str, rel_path: str, total_lines: int
    ) -> list[DetectedFeature]:
        """Detect Click and Typer CLI commands."""
        features: list[DetectedFeature] = []

        for pattern, framework in [(_CLICK_COMMAND, "click"), (_TYPER_COMMAND, "typer")]:
            for match in pattern.finditer(content):
                after = content[match.end():]
                func_match = _CLI_FUNC.search(after)
                func_name = func_match.group(1) if func_match else "unknown"
                line_number = content[:match.start()].count("\n") + 1
                loc = self._estimate_feature_loc(content, match.start(), total_lines)
                features.append(
                    DetectedFeature(
                        name=func_name,
                        category="cli_command",
                        file_path=rel_path,
                        line_number=line_number,
                        framework=framework,
                        loc=loc,
                        is_exported=False,
                    )
                )

        return features

    # ── Roadmap Cross-Reference ─────────────────────────────────────

    def _cross_reference_roadmap(
        self, features: list[DetectedFeature]
    ) -> tuple[dict[str, list[FeatureMapping]], list[UntrackedFeature]]:
        """Cross-reference features against roadmap items.

        Returns:
            Tuple of (roadmap_mappings, untracked_features).
            roadmap_mappings is keyed by feature name.
        """
        if not self.roadmap:
            return {}, []

        # Build list of roadmap items with their keywords
        roadmap_items: list[tuple[str, list[str]]] = []
        for milestone in self.roadmap.milestones:
            for item in milestone.items:
                keywords = _extract_keywords(item.text)
                roadmap_items.append((item.text, keywords))

        mappings: dict[str, list[FeatureMapping]] = {}
        untracked: list[UntrackedFeature] = []

        for feature in features:
            feature_keywords = _extract_keywords(feature.name)
            # Also extract keywords from the file path
            path_keywords = _extract_keywords(
                feature.file_path.replace("/", " ").replace("_", " ").replace("-", " ")
            )
            all_feature_keywords = list(set(feature_keywords + path_keywords))

            best_confidence = 0.0
            best_mapping: FeatureMapping | None = None

            for item_text, item_keywords in roadmap_items:
                if not item_keywords or not all_feature_keywords:
                    continue

                # Calculate keyword overlap
                matched = [kw for kw in all_feature_keywords if kw in item_keywords]
                if not matched:
                    continue

                confidence = len(matched) / max(len(item_keywords), len(all_feature_keywords))
                confidence = min(confidence, 1.0)

                if confidence > best_confidence:
                    best_confidence = confidence
                    best_mapping = FeatureMapping(
                        feature=feature,
                        roadmap_item_text=item_text,
                        confidence=confidence,
                        matched_keywords=tuple(matched),
                    )

            if best_mapping and best_confidence >= 0.3:
                mappings.setdefault(feature.name, []).append(best_mapping)
            elif feature.loc >= 50:
                untracked.append(
                    UntrackedFeature(
                        feature=feature,
                        reason=f"No roadmap match at confidence >= 0.3 for {feature.name} ({feature.loc} LOC)",
                    )
                )

        return mappings, untracked

    # ── Coupling Analysis (Task 13.9) ───────────────────────────────

    def _analyze_coupling(
        self, features: list[DetectedFeature]
    ) -> tuple[dict[str, int], list[dict]]:
        """Count how many files import each detected feature/module.

        Returns:
            Tuple of (import_counts, most_coupled).
            import_counts: feature_name -> number of importing files.
            most_coupled: top 10 entries sorted by import count descending.
        """
        # Build map of relative file paths -> module identifiers they define
        # For Python: src/core/foo.py defines module "foo" and path "src.core.foo"
        # For TS: src/components/Foo.tsx defines "Foo"
        module_to_feature: dict[str, str] = {}
        for feat in features:
            # Direct name match
            module_to_feature[feat.name] = feat.name
            # Module path for Python (e.g. "reconciliation" from src/core/reconciliation.py)
            stem = Path(feat.file_path).stem
            if stem not in module_to_feature:
                module_to_feature[stem] = feat.name

        # Count imports across all code files
        import_counts: dict[str, int] = {f.name: 0 for f in features}
        import_files: dict[str, set[str]] = {f.name: set() for f in features}

        for file_path in self._iter_code_files():
            try:
                content = file_path.read_text(errors="ignore")
            except OSError:
                continue

            rel_path = str(file_path.relative_to(self.project_path))
            ext = file_path.suffix.lower()

            imported_names: set[str] = set()

            if ext == ".py":
                imported_names = self._extract_python_imports(content)
            elif ext in (".ts", ".tsx", ".jsx", ".js", ".mjs"):
                imported_names = self._extract_ts_imports(content)

            # Match imported names to features
            for imported in imported_names:
                feat_name = module_to_feature.get(imported)
                if feat_name and feat_name in import_counts:
                    # Don't count self-imports
                    matching_features = [
                        f for f in features
                        if f.name == feat_name and f.file_path == rel_path
                    ]
                    if not matching_features:
                        import_counts[feat_name] += 1
                        import_files[feat_name].add(rel_path)

        # Build most_coupled (top 10)
        sorted_features = sorted(
            import_counts.items(),
            key=lambda x: x[1],
            reverse=True,
        )
        most_coupled: list[dict] = []
        for name, count in sorted_features[:10]:
            if count > 0:
                most_coupled.append({
                    "name": name,
                    "import_count": count,
                    "files_importing": sorted(import_files[name]),
                })

        return import_counts, most_coupled

    def _extract_python_imports(self, content: str) -> set[str]:
        """Extract imported module/symbol names from Python source."""
        names: set[str] = set()
        for match in _PYTHON_IMPORT.finditer(content):
            from_module = match.group(1)
            import_module = match.group(2)
            module = from_module or import_module
            if module:
                # Add the full module and the last component
                parts = module.split(".")
                names.add(parts[-1])
                # Also check for specific imports on the same line
                line_start = content.rfind("\n", 0, match.start()) + 1
                line_end = content.find("\n", match.end())
                if line_end == -1:
                    line_end = len(content)
                line = content[line_start:line_end]
                # from X import A, B, C
                import_match = re.search(r"import\s+(.+)", line)
                if import_match:
                    for symbol in import_match.group(1).split(","):
                        symbol = symbol.strip().split(" as ")[0].strip()
                        if symbol and symbol != "*":
                            names.add(symbol)
        return names

    def _extract_ts_imports(self, content: str) -> set[str]:
        """Extract imported module/symbol names from TypeScript/JS source."""
        names: set[str] = set()
        for match in _TS_IMPORT.finditer(content):
            module_path = match.group(1) or match.group(2)
            if module_path:
                # Get the last path segment as the module name
                parts = module_path.rstrip("/").split("/")
                last = parts[-1] if parts else ""
                # Strip extension
                last = re.sub(r"\.\w+$", "", last)
                if last:
                    names.add(last)

            # Also extract named imports: import { A, B } from '...'
            line_start = content.rfind("\n", 0, match.start()) + 1
            line_end = content.find("\n", match.end())
            if line_end == -1:
                line_end = len(content)
            line = content[line_start:line_end]
            brace_match = re.search(r"\{([^}]+)\}", line)
            if brace_match:
                for symbol in brace_match.group(1).split(","):
                    symbol = symbol.strip().split(" as ")[0].strip()
                    if symbol:
                        names.add(symbol)

            # Default import: import Foo from '...'
            default_match = re.match(r"import\s+([A-Z]\w+)\s+from", line)
            if default_match:
                names.add(default_match.group(1))

        return names

    # ── Helpers ──────────────────────────────────────────────────────

    def _iter_code_files(self):
        """Yield all code files in the project, skipping ignored directories."""
        all_extensions = set()
        for exts in _CODE_EXTENSIONS.values():
            all_extensions.update(exts)

        for file_path in self.project_path.rglob("*"):
            if not file_path.is_file():
                continue
            if file_path.suffix.lower() not in all_extensions:
                continue
            # Skip ignored directories
            parts = file_path.relative_to(self.project_path).parts
            if any(part in _IGNORED_DIRS for part in parts):
                continue
            yield file_path

    @staticmethod
    def _estimate_feature_loc(content: str, start_pos: int, total_lines: int) -> int:
        """Estimate lines of code for a feature starting at start_pos.

        Uses a heuristic: count lines until the next top-level definition
        (function, class, or export at column 0) or end of file.
        """
        lines = content[start_pos:].splitlines()
        if not lines:
            return 0

        count = 0
        for i, line in enumerate(lines):
            if i == 0:
                count += 1
                continue
            # Stop at next top-level definition
            if re.match(r"^(export\s+|def\s+|class\s+|async\s+def\s+|function\s+|@)", line):
                break
            count += 1

        return min(count, total_lines)


def _extract_keywords(text: str) -> list[str]:
    """Extract meaningful keywords from text for matching.

    Duplicated from reconciliation.py per spec to keep modules independent.
    """
    # Remove markdown and special chars
    text = re.sub(r"\[.*?\]|\(.*?\)|[*_`]", "", text)

    # Extract words
    words = re.findall(r"\b\w+\b", text.lower())

    # Filter out common words and short words
    common_words = {
        "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
        "of", "with", "by", "from", "up", "about", "into", "through", "during",
        "including", "add", "create", "implement", "update", "fix", "remove",
        "show", "display", "handle", "support", "use", "make", "set", "get",
        "new", "all", "each", "when", "not", "also", "based",
    }
    return [w for w in words if len(w) >= 3 and w not in common_words]
