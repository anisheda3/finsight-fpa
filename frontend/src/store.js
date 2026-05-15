/**
 * Lightweight in-memory store that survives React page navigation.
 * Avoids re-fetching data every time the user switches tabs.
 */

const _cache = {};
const _listeners = {};

export function getCache(key) {
  return _cache[key];
}

export function setCache(key, value) {
  _cache[key] = value;
  (_listeners[key] || []).forEach(fn => fn(value));
}

export function subscribe(key, fn) {
  if (!_listeners[key]) _listeners[key] = [];
  _listeners[key].push(fn);
  return () => {
    _listeners[key] = _listeners[key].filter(f => f !== fn);
  };
}

/** Persisted company ID — survives page switches */
export function getCompanyId() {
  return _cache.__companyId || localStorage.getItem('companyId') || '';
}

export function setCompanyId(id) {
  _cache.__companyId = id;
  localStorage.setItem('companyId', id);
}
