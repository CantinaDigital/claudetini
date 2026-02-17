/**
 * Bootstrap Progress View
 *
 * Shows real-time progress during bootstrap process.
 * Connects to SSE endpoint for live updates.
 */

import { useEffect, useState } from 'react';
import { API_BASE_URL } from '../../api/backend';

interface BootstrapProgress {
  type: 'progress' | 'complete' | 'error';
  progress?: number;
  message?: string;
  step?: string;
  step_type?: string;
  status?: string;
  result?: any;
  error?: string;
}

interface BootstrapProgressViewProps {
  sessionId: string;
  onComplete: (success: boolean, result?: any) => void;
  onCancel?: () => void;
}

/** Map status to mc-token hex values (from tailwind.config.js) for SVG stroke */
const STROKE_COLORS = {
  failed: '#f87171',    // mc-red
  completed: '#34d399', // mc-green
  running: '#8b7cf6',   // mc-accent
} as const;

export function BootstrapProgressView({
  sessionId,
  onComplete,
  onCancel,
}: BootstrapProgressViewProps) {
  const [progress, setProgress] = useState(0);
  const [message, setMessage] = useState('Initializing bootstrap...');
  const [step, setStep] = useState('0/5');
  const [logs, setLogs] = useState<string[]>([]);
  const [status, setStatus] = useState<'running' | 'completed' | 'failed'>('running');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Connect to SSE endpoint
    const eventSource = new EventSource(
      `${API_BASE_URL}/api/bootstrap/stream/${sessionId}`
    );

    eventSource.onmessage = (event) => {
      try {
        const data: BootstrapProgress = JSON.parse(event.data);

        if (data.type === 'progress') {
          setProgress(data.progress || 0);
          setMessage(data.message || '');
          setStep(data.step || '');

          // Add to logs
          if (data.message) {
            setLogs((prev) => [...prev, `[${data.step}] ${data.message}`]);
          }
        } else if (data.type === 'complete') {
          setStatus(data.status as 'completed' | 'failed');
          setProgress(100);

          if (data.status === 'completed') {
            setMessage('Bootstrap complete!');
            onComplete(true, data.result);
          } else {
            setMessage('Bootstrap failed');
            setError(data.error || 'Unknown error');
            onComplete(false);
          }

          eventSource.close();
        } else if (data.type === 'error') {
          setStatus('failed');
          setError(data.error || 'Unknown error');
          setMessage('Bootstrap failed');
          onComplete(false);
          eventSource.close();
        }
      } catch (err) {
        console.error('Failed to parse SSE message:', err);
      }
    };

    eventSource.onerror = (err) => {
      console.error('SSE error:', err);
      setStatus('failed');
      setError('Connection lost to bootstrap process');
      eventSource.close();
    };

    return () => {
      eventSource.close();
    };
  }, [sessionId, onComplete]);

  return (
    <div className="min-h-screen bg-mc-bg text-mc-text-0 flex items-center justify-center p-8">
      <div className="max-w-2xl w-full">
        {/* Header */}
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold mb-2">
            {status === 'running' ? 'Bootstrapping Project' : status === 'completed' ? 'Bootstrap Complete' : 'Bootstrap Failed'}
          </h1>
          <p className="text-mc-text-2">
            {status === 'running'
              ? 'Setting up your project for Claude Code...'
              : status === 'completed'
              ? 'Your project is ready!'
              : 'Something went wrong'}
          </p>
        </div>

        {/* Progress Ring/Circle */}
        <div className="bg-mc-surface-0 rounded-xl p-8 mb-6 flex flex-col items-center">
          {/* Circular progress */}
          <div className="relative inline-flex items-center justify-center mb-6">
            <svg width="180" height="180" className="transform -rotate-90">
              {/* Background circle */}
              <circle
                cx="90"
                cy="90"
                r="80"
                fill="none"
                className="stroke-mc-surface-2"
                strokeWidth="8"
              />

              {/* Progress circle */}
              <circle
                cx="90"
                cy="90"
                r="80"
                fill="none"
                stroke={STROKE_COLORS[status]}
                strokeWidth="8"
                strokeLinecap="round"
                strokeDasharray={`${2 * Math.PI * 80}`}
                strokeDashoffset={`${2 * Math.PI * 80 * (1 - progress / 100)}`}
                className="transition-all duration-500"
              />
            </svg>

            {/* Progress text */}
            <div className="absolute inset-0 flex flex-col items-center justify-center">
              <div className="text-4xl font-bold tabular-nums">
                {Math.round(progress)}%
              </div>
              <div className="text-sm text-mc-text-2 mt-1">{step}</div>
            </div>
          </div>

          {/* Current step message */}
          <p className="text-lg text-center">{message}</p>

          {/* Status icon */}
          {status === 'completed' && (
            <div className="mt-4">
              <svg
                className="w-12 h-12 text-mc-green"
                fill="currentColor"
                viewBox="0 0 20 20"
              >
                <path
                  fillRule="evenodd"
                  d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
                  clipRule="evenodd"
                />
              </svg>
            </div>
          )}

          {status === 'failed' && error && (
            <div className="mt-4 p-4 bg-mc-red-muted border border-mc-red-border rounded-lg">
              <p className="text-mc-red text-sm">{error}</p>
            </div>
          )}
        </div>

        {/* Activity Log */}
        <div className="bg-mc-surface-0 rounded-xl p-6 mb-6">
          <h3 className="text-sm font-semibold text-mc-text-2 mb-3">
            Activity Log
          </h3>
          <div className="bg-mc-bg rounded-lg p-4 max-h-48 overflow-y-auto font-mono text-sm space-y-1">
            {logs.length === 0 ? (
              <p className="text-mc-text-2">Waiting for updates...</p>
            ) : (
              logs.map((log, idx) => (
                <div key={idx} className="text-mc-text-2">
                  {log}
                </div>
              ))
            )}
          </div>
        </div>

        {/* Action Buttons */}
        <div className="flex gap-4 justify-center">
          {status === 'completed' && (
            <button
              onClick={() => onComplete(true)}
              className="px-6 py-3 bg-mc-green text-white rounded-lg font-semibold hover:bg-mc-green/80 transition-colors"
            >
              Continue to Dashboard
            </button>
          )}

          {status === 'failed' && (
            <>
              <button
                onClick={() => onComplete(false)}
                className="px-6 py-3 bg-mc-red text-white rounded-lg font-semibold hover:bg-mc-red/80 transition-colors"
              >
                Try Again
              </button>
              <button
                onClick={() => onCancel?.()}
                className="px-6 py-3 bg-mc-surface-2 text-mc-text-0 rounded-lg font-semibold hover:bg-mc-surface-3 transition-colors"
              >
                Cancel
              </button>
            </>
          )}

          {status === 'running' && onCancel && (
            <button
              onClick={onCancel}
              className="px-6 py-3 bg-transparent border-2 border-mc-border-2 text-mc-text-2 rounded-lg font-semibold hover:border-mc-border-2 hover:text-mc-text-0 transition-colors"
            >
              Cancel
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
