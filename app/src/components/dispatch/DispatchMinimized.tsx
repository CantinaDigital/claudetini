import { useDispatchManager } from "../../managers/dispatchManager";

function secondsToDuration(totalSeconds: number): string {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}

/**
 * Minimized indicator shown in bottom-right when dispatch is running but overlay is hidden.
 * Clicking "Show" restores the full overlay.
 */
export function DispatchMinimized() {
  const isDispatching = useDispatchManager((s) => s.isDispatching);
  const showOverlay = useDispatchManager((s) => s.showOverlay);
  const elapsedSeconds = useDispatchManager((s) => s.elapsedSeconds);

  if (!isDispatching || showOverlay) {
    return null;
  }

  return (
    <div className="fixed right-5 bottom-4 z-[9997] bg-mc-surface-1 border border-mc-border-1 rounded-lg py-2 px-2.5 flex items-center gap-2.5">
      <span className="text-[11px] text-mc-text-2">
        Claude dispatch running ({secondsToDuration(elapsedSeconds)})
      </span>
      <button
        onClick={() => useDispatchManager.setState({ showOverlay: true })}
        className="border border-mc-border-1 rounded-md bg-transparent text-mc-text-1 text-[11px] py-1 px-2 cursor-pointer"
      >
        Show
      </button>
    </div>
  );
}
