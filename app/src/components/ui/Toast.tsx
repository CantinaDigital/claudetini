import { useEffect, useState } from "react";
import type { ReactNode } from "react";

export type ToastType = "success" | "error" | "warning" | "info";

export interface ToastData {
  id: string;
  type: ToastType;
  title: string;
  message?: string;
  duration?: number; // ms, default 4000
}

interface ToastProps {
  toast: ToastData;
  onDismiss: (id: string) => void;
}

const iconMap: Record<ToastType, ReactNode> = {
  success: "\u2713",
  error: "\u2715",
  warning: "!",
  info: "i",
};

const colorMap: Record<ToastType, { bg: string; border: string; icon: string }> = {
  success: { bg: "bg-mc-green-muted", border: "border-mc-green-border", icon: "bg-mc-green" },
  error: { bg: "bg-mc-red-muted", border: "border-mc-red-border", icon: "bg-mc-red" },
  warning: { bg: "bg-mc-amber-muted", border: "border-mc-amber-border", icon: "bg-mc-amber" },
  info: { bg: "bg-mc-accent-muted", border: "border-mc-accent-border", icon: "bg-mc-accent" },
};

function Toast({ toast, onDismiss }: ToastProps) {
  const [isExiting, setIsExiting] = useState(false);
  const colors = colorMap[toast.type];

  useEffect(() => {
    const duration = toast.duration ?? 4000;
    const exitTimer = setTimeout(() => setIsExiting(true), duration - 300);
    const removeTimer = setTimeout(() => onDismiss(toast.id), duration);
    return () => {
      clearTimeout(exitTimer);
      clearTimeout(removeTimer);
    };
  }, [toast.id, toast.duration, onDismiss]);

  return (
    <div
      className={`flex items-start gap-3 py-3 px-4 rounded-lg border backdrop-blur-sm shadow-[0_4px_12px_rgba(0,0,0,0.4)] font-sans min-w-[280px] max-w-[400px] cursor-pointer transition-all duration-300 ease-out ${colors.bg} ${colors.border}`}
      style={{
        opacity: isExiting ? 0 : 1,
        transform: isExiting ? "translateX(100%)" : "translateX(0)",
      }}
      onClick={() => onDismiss(toast.id)}
    >
      <div className={`w-5 h-5 rounded-full flex items-center justify-center text-[11px] font-bold text-black shrink-0 ${colors.icon}`}>
        {iconMap[toast.type]}
      </div>
      <div className="flex-1">
        <div className="text-mc-text-0 text-[13px] font-semibold">
          {toast.title}
        </div>
        {toast.message && (
          <div className="text-mc-text-2 text-xs mt-0.5">
            {toast.message}
          </div>
        )}
      </div>
    </div>
  );
}

// Toast container that renders all active toasts
interface ToastContainerProps {
  toasts: ToastData[];
  onDismiss: (id: string) => void;
}

export function ToastContainer({ toasts, onDismiss }: ToastContainerProps) {
  if (toasts.length === 0) return null;

  return (
    <div className="fixed bottom-5 right-5 flex flex-col gap-2 z-[9999] pointer-events-none">
      {toasts.map((toast) => (
        <div key={toast.id} className="pointer-events-auto">
          <Toast toast={toast} onDismiss={onDismiss} />
        </div>
      ))}
    </div>
  );
}

// Simple hook for managing toasts
let toastId = 0;
let listeners: Array<(toasts: ToastData[]) => void> = [];
let toastQueue: ToastData[] = [];

function notifyListeners() {
  listeners.forEach((listener) => listener([...toastQueue]));
}

export const toast = {
  show: (type: ToastType, title: string, message?: string, duration?: number) => {
    const id = `toast-${++toastId}`;
    toastQueue.push({ id, type, title, message, duration });
    notifyListeners();
    return id;
  },
  success: (title: string, message?: string) => toast.show("success", title, message),
  error: (title: string, message?: string) => toast.show("error", title, message, 6000),
  warning: (title: string, message?: string) => toast.show("warning", title, message),
  info: (title: string, message?: string) => toast.show("info", title, message),
  dismiss: (id: string) => {
    toastQueue = toastQueue.filter((t) => t.id !== id);
    notifyListeners();
  },
  subscribe: (listener: (toasts: ToastData[]) => void) => {
    listeners.push(listener);
    return () => {
      listeners = listeners.filter((l) => l !== listener);
    };
  },
};

// Hook for components to consume toasts
export function useToasts() {
  const [toasts, setToasts] = useState<ToastData[]>([]);

  useEffect(() => {
    return toast.subscribe(setToasts);
  }, []);

  return { toasts, dismiss: toast.dismiss };
}
