# Claudetini App - Frontend Guide

> React + TypeScript + Tailwind frontend for the Claudetini desktop application.

## Overview

This is the Tauri desktop frontend for Claudetini. It communicates with a Python FastAPI sidecar running on port 9876 for all data operations.

**Tech Stack:**
- React 19 + TypeScript 5.8
- Vite 7 (bundler)
- Tailwind CSS 3.4
- Zustand 5 (state management)
- Tauri 2 (desktop shell)

## Architecture

```
app/
├── src/
│   ├── main.tsx              # React entry point
│   ├── App.tsx               # Root component, tab router
│   ├── api/
│   │   └── backend.ts        # HTTP client to Python sidecar
│   ├── store/
│   │   └── index.ts          # Zustand state management
│   ├── types/
│   │   └── index.ts          # All TypeScript interfaces
│   ├── styles/
│   │   └── tokens.ts         # Design tokens (colors, spacing)
│   └── components/
│       ├── layout/           # Dashboard, TabBar
│       ├── overview/         # Overview tab components
│       ├── roadmap/          # Roadmap tab
│       ├── timeline/         # Timeline tab
│       ├── gates/            # Quality gates tab
│       ├── logs/             # Logs tab
│       ├── settings/         # Settings tab
│       └── ui/               # Reusable primitives (Button, Tag, etc.)
├── src-tauri/                # Rust Tauri shell (minimal)
└── python-sidecar/           # FastAPI backend
```

## Code Conventions

### TypeScript
- Use strict mode (enabled in tsconfig.json)
- Prefer `interface` over `type` for object shapes
- Use explicit return types for exported functions
- No `any` - use `unknown` if type is truly unknown

### React
- Functional components only (no class components)
- Use hooks for all state and effects
- Prefer composition over prop drilling
- Colocate component styles with components

### Naming
- `PascalCase` for components and types/interfaces
- `camelCase` for functions, variables, hooks
- `SCREAMING_SNAKE_CASE` for constants
- Files: `PascalCase.tsx` for components, `camelCase.ts` for utilities

### Component Structure
```tsx
// Imports (external, then internal, then types)
import { useState } from 'react';
import { useStore } from '../store';
import type { Project } from '../types';

// Types specific to this component
interface Props {
  project: Project;
  onSelect: (id: string) => void;
}

// Component
export function ProjectCard({ project, onSelect }: Props) {
  // Hooks first
  const [isHovered, setIsHovered] = useState(false);

  // Handlers
  const handleClick = () => onSelect(project.id);

  // Render
  return (
    <div onClick={handleClick}>
      {project.name}
    </div>
  );
}
```

### Styling
- Use Tailwind `mc-*` classes for all token colors. Import `t` from tokens only for SVG attributes and computed dynamic values.
- Design tokens defined in `styles/tokens.ts`, mirrored in `tailwind.config.js` under the `mc` namespace.
- Dark mode is the default (Mission Control theme).
- All custom colors use the `mc-` prefix (e.g., `bg-mc-bg`, `text-mc-text-1`, `border-mc-accent-border`).

### State Management
- Global state in Zustand store (`store/index.ts`)
- Local UI state with useState/useReducer
- Async operations return Promises, errors handled in store
- Never mutate state directly

## API Communication

All backend calls go through `api/backend.ts`:

```typescript
// Example: Fetch project data
const project = await api.getProject(projectId);

// Example: Run quality gates
const results = await api.runGates(projectId);
```

The sidecar runs on `http://127.0.0.1:9876`. Endpoints:
- `/api/project/*` - Project CRUD
- `/api/roadmap/*` - Roadmap parsing
- `/api/timeline/*` - Session timeline
- `/api/gates/*` - Quality gates
- `/api/git/*` - Git operations
- `/api/dispatch` - Claude Code dispatch

## Commands

```bash
# Development (frontend only)
npm run dev

# Development (with backend)
npm run dev:all

# Development (with Tauri)
npm run tauri:dev

# Build for production
npm run build

# Preview production build
npm run preview

# Start backend only
npm run backend
```

## Design System

All tokens are defined in `styles/tokens.ts` and mirrored as Tailwind `mc-*` utilities in `tailwind.config.js`.

### Colors

| Token | Hex / Value | Tailwind class (example) |
|-------|-------------|--------------------------|
| **Background** | `#0c0c0f` | `bg-mc-bg` |
| **Surface 0** | `#111116` | `bg-mc-surface-0` |
| **Surface 1** | `#18181f` | `bg-mc-surface-1` |
| **Surface 2** | `#1f1f28` | `bg-mc-surface-2` |
| **Surface 3** | `#262630` | `bg-mc-surface-3` |
| **Border 0** | `rgba(255,255,255,0.04)` | `border-mc-border-0` |
| **Border 1** | `rgba(255,255,255,0.07)` | `border-mc-border-1` |
| **Border 2** | `rgba(255,255,255,0.12)` | `border-mc-border-2` |
| **Text 0** (brightest) | `#f0f0f5` | `text-mc-text-0` |
| **Text 1** | `#c8c8d4` | `text-mc-text-1` |
| **Text 2** (muted) | `#8b8b9e` | `text-mc-text-2` |
| **Text 3** (dimmest) | `#5c5c6e` | `text-mc-text-3` |
| **Accent** | `#8b7cf6` | `text-mc-accent`, `bg-mc-accent` |
| **Accent muted** | `rgba(139,124,246,0.12)` | `bg-mc-accent-muted` |
| **Accent border** | `rgba(139,124,246,0.25)` | `border-mc-accent-border` |
| **Green (success)** | `#34d399` | `text-mc-green`, `bg-mc-green` |
| **Green muted** | `rgba(52,211,153,0.1)` | `bg-mc-green-muted` |
| **Green border** | `rgba(52,211,153,0.2)` | `border-mc-green-border` |
| **Red (error)** | `#f87171` | `text-mc-red`, `bg-mc-red` |
| **Red muted** | `rgba(248,113,113,0.08)` | `bg-mc-red-muted` |
| **Red border** | `rgba(248,113,113,0.18)` | `border-mc-red-border` |
| **Amber (warning)** | `#fbbf24` | `text-mc-amber`, `bg-mc-amber` |
| **Amber muted** | `rgba(251,191,36,0.08)` | `bg-mc-amber-muted` |
| **Amber border** | `rgba(251,191,36,0.18)` | `border-mc-amber-border` |
| **Cyan** | `#22d3ee` | `text-mc-cyan`, `bg-mc-cyan` |
| **Cyan muted** | `rgba(34,211,238,0.12)` | `bg-mc-cyan-muted` |
| **Cyan border** | `rgba(34,211,238,0.25)` | `border-mc-cyan-border` |

### Typography

- **Sans:** Satoshi, DM Sans, -apple-system, sans-serif (`font-sans`)
- **Mono:** IBM Plex Mono, JetBrains Mono, monospace (`font-mono`)

## Testing

Tests use Vitest (not yet configured). When adding tests:
- Place in `__tests__/` directories or `*.test.tsx` files
- Mock API calls with MSW
- Test components with React Testing Library
