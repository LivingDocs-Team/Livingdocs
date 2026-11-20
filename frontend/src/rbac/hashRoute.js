// Minimal hash router (#/path). Hash URLs work with the existing nginx/vite config and need no
// router dependency; typing a URL such as /#/review/queue opens that screen directly.
import { useSyncExternalStore } from 'react';

function readPath() {
  const { hash } = window.location;
  return hash.startsWith('#') ? hash.slice(1) : '';
}

function subscribe(onChange) {
  window.addEventListener('hashchange', onChange);
  return () => window.removeEventListener('hashchange', onChange);
}

export function useHashPath() {
  return useSyncExternalStore(subscribe, readPath, () => '');
}

export function hrefFor(path) {
  return `#${path}`;
}

/** Changes the current screen. `replace` is used for redirects so Back does not loop. */
export function navigate(path, { replace = false } = {}) {
  if (readPath() === path) return;
  if (replace) window.location.replace(hrefFor(path));
  else window.location.hash = path;
}
