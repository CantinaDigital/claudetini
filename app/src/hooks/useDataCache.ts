/**
 * In-memory cache for API responses.
 *
 * TTL tiers (longest to shortest):
 *   - sessions:  5 min — old sessions are immutable once ended
 *   - timeline:  2 min — timeline changes only when a new session starts/ends
 *   - advice:    5 min — AI-generated dispatch advice (expensive)
 *   - commits:   30 s  — only changes on new commits
 *   - git:       15 s  — working tree can change frequently
 *   - default:   60 s  — everything else
 */

interface CacheEntry<T> {
  data: T;
  timestamp: number;
}

/** TTL lookup by key prefix (order matters — first match wins) */
const TTL_TIERS: [string, number][] = [
  ["sessions:", 300_000],  // 5 min  — immutable past sessions
  ["timeline:", 120_000],  // 2 min  — changes infrequently
  ["advice:",   300_000],  // 5 min  — expensive AI calls
  ["commits:",   30_000],  // 30 s   — new commits are less frequent
  ["git:",       15_000],  // 15 s   — working tree changes often
];

const DEFAULT_TTL = 60_000; // 1 min

const cache = new Map<string, CacheEntry<unknown>>();

function ttlForKey(key: string): number {
  for (const [prefix, ttl] of TTL_TIERS) {
    if (key.startsWith(prefix)) return ttl;
  }
  return DEFAULT_TTL;
}

export function getCached<T>(key: string): T | null {
  const entry = cache.get(key);
  if (!entry) return null;

  if (Date.now() - entry.timestamp > ttlForKey(key)) {
    cache.delete(key);
    return null;
  }

  return entry.data as T;
}

export function setCache<T>(key: string, data: T): void {
  cache.set(key, { data, timestamp: Date.now() });
}

export function invalidateCache(keyPrefix?: string): void {
  if (!keyPrefix) {
    cache.clear();
    return;
  }

  for (const key of cache.keys()) {
    if (key.startsWith(keyPrefix)) {
      cache.delete(key);
    }
  }
}
