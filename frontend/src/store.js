// Minimal observable state. `set(patch)` merges and notifies listeners with
// the set of keys that actually changed, so renderers can skip work.
export function createStore(initial) {
  let state = { ...initial };
  const listeners = new Set();
  return {
    get: () => state,
    set(patch) {
      const changed = new Set();
      for (const [k, v] of Object.entries(patch)) {
        if (state[k] !== v) changed.add(k);
      }
      if (!changed.size) return;
      state = { ...state, ...patch };
      for (const fn of listeners) fn(state, changed);
    },
    subscribe(fn) { listeners.add(fn); return () => listeners.delete(fn); },
  };
}
