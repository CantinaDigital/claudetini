/**
 * Domain Manager Layer — barrel exports.
 *
 * Each manager is a Zustand store that owns the complete lifecycle
 * of a domain: state + API calls + polling + cleanup.
 */

export { useProjectManager } from "./projectManager";
export { useDispatchManager } from "./dispatchManager";
export type { DispatchContext } from "./dispatchManager";
export type { QueuedDispatch } from "../types";
export { useReconciliationManager } from "./reconciliationManager";
export { useGitManager } from "./gitManager";
