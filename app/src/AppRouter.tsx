/**
 * App Router - Screen State Machine
 *
 * Routes between:
 * - Project Picker (first-time experience)
 * - Readiness Scorecard (check if project is ready)
 * - Bootstrap Wizard (set up missing artifacts)
 * - Dashboard (main app - existing App.tsx)
 */

import React from 'react';
import { useEffect, useState } from 'react';
import { useProjectManager } from './managers/projectManager';
import { ProjectPickerView } from './components/project/ProjectPickerView';
import { ScorecardView } from './components/scorecard/ScorecardView';
import { BootstrapWizard } from './components/bootstrap/BootstrapWizard';
import App from './App'; // Existing dashboard
import { initBackend, api } from './api/backend';

class RootErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { hasError: boolean; error: Error | null }
> {
  constructor(props: { children: React.ReactNode }) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error('Root error boundary caught:', error, info);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{
          minHeight: '100vh',
          background: '#0a0a0f',
          color: '#e4e4e7',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          fontFamily: 'Inter, system-ui, sans-serif',
          padding: 32,
        }}>
          <div style={{ fontSize: 24, fontWeight: 700, marginBottom: 12 }}>
            Something went wrong
          </div>
          <div style={{ fontSize: 13, color: '#8b8b94', marginBottom: 24, maxWidth: 480, textAlign: 'center' }}>
            {this.state.error?.message || 'An unexpected error occurred'}
          </div>
          <button
            onClick={() => window.location.reload()}
            style={{
              background: '#3b82f6',
              color: '#fff',
              border: 'none',
              borderRadius: 8,
              padding: '10px 24px',
              fontSize: 14,
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            Reload Application
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

function AppRouterInner() {
  const currentScreen = useProjectManager((s) => s.currentScreen);
  const setScreen = useProjectManager((s) => s.setScreen);
  const currentProject = useProjectManager((s) => s.currentProject);
  const projects = useProjectManager((s) => s.projects);
  const isLoading = useProjectManager((s) => s.isLoading);
  const error = useProjectManager((s) => s.error);
  const loadProjects = useProjectManager((s) => s.loadProjects);
  const [backendReady, setBackendReady] = useState(false);
  const [registering, setRegistering] = useState(false);

  // Initialize backend and load projects on mount
  useEffect(() => {
    const init = async () => {
      try {
        await initBackend();
        setBackendReady(true);
        await loadProjects();
      } catch {
        // Backend not available — show picker anyway with warning banner
        setBackendReady(false);
      }
    };
    init();
  }, [loadProjects]);

  // When a project is opened, go straight to the dashboard (no readiness gate)
  const handleOpenProject = (project: any) => {
    useProjectManager.setState({ currentProject: project });
    setScreen('dashboard');
  };

  // Register a new project path
  const handleRegisterProject = async (path: string) => {
    setRegistering(true);
    try {
      const newProject = await api.registerProject(path);
      // Reload the full list so it shows up
      await loadProjects();
      // Auto-select the newly registered project
      useProjectManager.setState({ currentProject: newProject });
    } catch (err) {
      useProjectManager.setState({
        error: err instanceof Error ? err.message : "Failed to register project",
      });
    } finally {
      setRegistering(false);
    }
  };

  // Project Picker Screen (always reachable, even without backend)
  if (currentScreen === 'picker') {
    return (
      <ProjectPickerView
        projects={projects}
        selectedProjectId={currentProject?.id}
        loading={isLoading}
        registering={registering}
        backendConnected={backendReady}
        error={error}
        onSelectProject={(project) => {
          useProjectManager.setState({ currentProject: project });
        }}
        onOpenProject={handleOpenProject}
        onRegisterProject={handleRegisterProject}
        onRefresh={() => {
          loadProjects();
        }}
      />
    );
  }

  // Readiness Scorecard Screen (accessed on-demand from dashboard)
  if (currentScreen === 'scorecard' && currentProject) {
    return (
      <ScorecardView
        projectPath={currentProject.path}
        onBootstrap={() => {
          setScreen('bootstrap');
        }}
        onSkip={() => {
          setScreen('dashboard');
        }}
        onBack={() => {
          setScreen('dashboard');
        }}
      />
    );
  }

  // Bootstrap Wizard Screen
  if (currentScreen === 'bootstrap' && currentProject) {
    return (
      <BootstrapWizard
        projectPath={currentProject.path}
        onComplete={() => {
          setScreen('dashboard');
        }}
        onCancel={() => {
          setScreen('scorecard');
        }}
      />
    );
  }

  // Dashboard Screen (existing app)
  if (currentScreen === 'dashboard') {
    return <App />;
  }

  // Fallback - shouldn't happen
  return null;
}

export function AppRouter() {
  return (
    <RootErrorBoundary>
      <AppRouterInner />
    </RootErrorBoundary>
  );
}
