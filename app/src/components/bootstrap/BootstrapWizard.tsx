/**
 * Bootstrap Wizard
 *
 * Orchestrates the bootstrap flow:
 * 1. Show cost estimate
 * 2. Confirm with user
 * 3. Start bootstrap
 * 4. Show progress
 * 5. Handle completion
 */

import { useState, useEffect } from 'react';
import { BootstrapProgressView } from './BootstrapProgressView';
import { api } from '../../api/backend';

interface CostEstimate {
  total_tokens: number;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
  steps: number;
}

interface BootstrapWizardProps {
  projectPath: string;
  onComplete: () => void;
  onCancel: () => void;
}

type WizardScreen = 'estimate' | 'confirm' | 'progress' | 'result';

export function BootstrapWizard({
  projectPath,
  onComplete,
  onCancel,
}: BootstrapWizardProps) {
  const [screen, setScreen] = useState<WizardScreen>('estimate');
  const [estimate, setEstimate] = useState<CostEstimate | null>(null);
  const [estimateLoading, setEstimateLoading] = useState(true);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [skipOptions, setSkipOptions] = useState({
    skipGit: false,
    skipArchitecture: false,
  });

  // Fetch cost estimate on mount
  useEffect(() => {
    const fetchEstimate = async () => {
      try {
        const data = await api.estimateBootstrapCost(projectPath);
        setEstimate(data);
      } catch (err) {
        console.error('Failed to fetch cost estimate:', err);
      } finally {
        setEstimateLoading(false);
      }
    };

    fetchEstimate();
  }, [projectPath]);

  const handleStartBootstrap = async () => {
    try {
      const data = await api.startBootstrap(projectPath, {
        skipGit: skipOptions.skipGit,
        skipArchitecture: skipOptions.skipArchitecture,
      });
      setSessionId(data.session_id);
      setScreen('progress');
    } catch (err) {
      console.error('Failed to start bootstrap:', err);
    }
  };

  const handleBootstrapComplete = (success: boolean) => {
    if (success) {
      onComplete();
    } else {
      // Reset state and go back to estimate screen so user can retry
      setSessionId(null);
      setScreen('estimate');
    }
  };

  // Cost Estimate Screen
  if (screen === 'estimate') {
    return (
      <div className="min-h-screen bg-mc-bg text-mc-text-0 flex items-center justify-center p-8">
        <div className="max-w-2xl w-full">
          <div className="text-center mb-8">
            <h1 className="text-3xl font-bold mb-2">Bootstrap Project</h1>
            <p className="text-mc-text-2">
              Set up your project with Claude Code best practices
            </p>
          </div>

          {estimateLoading ? (
            <div className="bg-mc-surface-0 rounded-xl p-8 text-center">
              <div className="w-8 h-8 border-4 border-mc-accent border-t-transparent rounded-full animate-spin mx-auto mb-4"></div>
              <p className="text-mc-text-2">Calculating cost estimate...</p>
            </div>
          ) : estimate ? (
            <>
              {/* What will be created */}
              <div className="bg-mc-surface-0 rounded-xl p-6 mb-6">
                <h3 className="font-semibold mb-4">What will be created:</h3>
                <ul className="space-y-2">
                  <li className="flex items-center gap-2">
                    <svg className="w-5 h-5 text-mc-green" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                    </svg>
                    <span>.claude/planning/ROADMAP.md - Milestone-based development plan</span>
                  </li>
                  <li className="flex items-center gap-2">
                    <svg className="w-5 h-5 text-mc-green" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                    </svg>
                    <span>CLAUDE.md - Project instructions for Claude Code</span>
                  </li>
                  <li className="flex items-center gap-2">
                    <svg className="w-5 h-5 text-mc-green" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                    </svg>
                    <span>.gitignore - Sensible defaults for your project type</span>
                  </li>
                  <li className="flex items-center gap-2">
                    <svg className="w-5 h-5 text-mc-green" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                    </svg>
                    <span>docs/ARCHITECTURE.md - System design documentation</span>
                  </li>
                </ul>
              </div>

              {/* Cost estimate */}
              <div className="bg-mc-surface-0 rounded-xl p-6 mb-6">
                <h3 className="font-semibold mb-4">Estimated Cost:</h3>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <p className="text-sm text-mc-text-2">Total Steps</p>
                    <p className="text-2xl font-bold">{estimate.steps}</p>
                  </div>
                  <div>
                    <p className="text-sm text-mc-text-2">Estimated Tokens</p>
                    <p className="text-2xl font-bold">{estimate.total_tokens.toLocaleString()}</p>
                  </div>
                  <div className="col-span-2">
                    <p className="text-sm text-mc-text-2">Estimated Cost</p>
                    <p className="text-4xl font-bold text-mc-accent">
                      ${estimate.cost_usd.toFixed(2)} USD
                    </p>
                    <p className="text-xs text-mc-text-2 mt-1">
                      Actual cost may vary based on project complexity
                    </p>
                  </div>
                </div>
              </div>

              {/* Options */}
              <div className="bg-mc-surface-0 rounded-xl p-6 mb-6">
                <h3 className="font-semibold mb-4">Options:</h3>
                <div className="space-y-3">
                  <label className="flex items-center gap-3 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={skipOptions.skipGit}
                      onChange={(e) =>
                        setSkipOptions({ ...skipOptions, skipGit: e.target.checked })
                      }
                      className="w-4 h-4 rounded bg-mc-surface-2 border-mc-accent text-mc-accent focus:ring-mc-accent"
                    />
                    <span>Skip .gitignore (if you already have one)</span>
                  </label>
                  <label className="flex items-center gap-3 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={skipOptions.skipArchitecture}
                      onChange={(e) =>
                        setSkipOptions({ ...skipOptions, skipArchitecture: e.target.checked })
                      }
                      className="w-4 h-4 rounded bg-mc-surface-2 border-mc-accent text-mc-accent focus:ring-mc-accent"
                    />
                    <span>Skip architecture docs (optional)</span>
                  </label>
                </div>
              </div>

              {/* Actions */}
              <div className="flex gap-4 justify-center">
                <button
                  onClick={handleStartBootstrap}
                  className="px-6 py-3 bg-mc-accent text-white rounded-lg font-semibold hover:bg-mc-accent/80 transition-colors flex items-center gap-2"
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                  </svg>
                  Start Bootstrap
                </button>
                <button
                  onClick={onCancel}
                  className="px-6 py-3 bg-transparent border-2 border-mc-border-2 text-mc-text-2 rounded-lg font-semibold hover:border-mc-border-2 hover:text-mc-text-0 transition-colors"
                >
                  Cancel
                </button>
              </div>
            </>
          ) : (
            <div className="bg-mc-surface-0 rounded-xl p-8 text-center">
              <p className="text-mc-red mb-4">Failed to estimate cost</p>
              <button
                onClick={onCancel}
                className="px-6 py-3 bg-mc-surface-2 text-mc-text-0 rounded-lg font-semibold hover:bg-mc-surface-3 transition-colors"
              >
                Go Back
              </button>
            </div>
          )}
        </div>
      </div>
    );
  }

  // Progress Screen
  if (screen === 'progress' && sessionId) {
    return (
      <BootstrapProgressView
        sessionId={sessionId}
        onComplete={handleBootstrapComplete}
        onCancel={onCancel}
      />
    );
  }

  // Fallback
  return null;
}
