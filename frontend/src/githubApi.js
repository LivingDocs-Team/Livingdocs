import { csrfHeaders } from './csrf';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '';

async function request(path, { method = 'GET', body, text = false } = {}) {

  let response;
  try {
    const headers = body === undefined ? {} : { 'Content-Type': 'application/json' };
    response = await fetch(`${API_BASE_URL}${path}`, {
      method,
      headers: ['POST', 'PUT', 'PATCH', 'DELETE'].includes(method.toUpperCase())
        ? await csrfHeaders(headers, API_BASE_URL)
        : headers,
      credentials: 'include',
      signal: AbortSignal.timeout(180000),
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch (error) {
    if (error?.name === 'TimeoutError') {
      throw new Error('The request timed out. Please try again.', { cause: error });
    }
    throw new Error('Could not connect to the GitHub integration service.', { cause: error });
  }

  if (response.status === 204) return null;
  const data = text
    ? await response.text()
    : await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 401) {
      window.dispatchEvent(new Event('livingdocs:unauthenticated'));
    }
    const message = !text && data && typeof data.message === 'string'
      ? data.message
      : `Request failed (HTTP ${response.status}).`;
    const error = new Error(message);
    error.status = response.status;
    error.code = !text && data ? data.code : undefined;
    error.retryAfter = response.headers.get('Retry-After');
    throw error;
  }
  return data;
}

export function githubApi(path, options) {
  return request(path, options);
}

export function githubApiText(path, options) {
  return request(path, { ...options, text: true });
}
