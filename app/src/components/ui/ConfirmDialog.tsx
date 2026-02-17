import { Button } from "./Button";

interface ConfirmDialogProps {
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmDialog({
  title,
  message,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  danger = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  return (
    <div
      className="fixed inset-0 bg-black/60 z-[200] flex items-center justify-center"
      onClick={onCancel}
    >
      <div
        className={`w-[380px] bg-mc-surface-1 rounded-xl border animate-fade-in overflow-hidden ${
          danger ? "border-mc-red-border" : "border-mc-border-1"
        }`}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="px-5 py-4 border-b border-mc-border-0">
          <div className={`text-sm font-bold ${danger ? "text-mc-red" : "text-mc-text-0"}`}>
            {title}
          </div>
        </div>

        {/* Body */}
        <div className="px-5 py-4 text-[12.5px] leading-relaxed text-mc-text-2">
          {message}
        </div>

        {/* Actions */}
        <div className="flex justify-end gap-2 px-5 py-3 border-t border-mc-border-0">
          <Button onClick={onCancel}>{cancelLabel}</Button>
          <Button danger={danger} primary={!danger} onClick={onConfirm}>
            {confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}
