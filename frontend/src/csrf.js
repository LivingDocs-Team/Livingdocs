export async function fetchCsrfToken(apiBaseUrl = '') {
  const baseUrl = apiBaseUrl.replace(/\/$/, '');
  const response = await fetch(`${baseUrl}/api/auth/csrf`, {
    credentials: 'include',
    signal: AbortSignal.timeout(15000),
  });
  if (!response.ok) throw new Error('Could not obtain a request security token.');
  const payload = await response.json();
  if (typeof payload?.token !== 'string' || payload.token.length === 0) {
    throw new Error('The backend returned an invalid request security token.');
  }
  return payload.token;
}

export async function csrfHeaders(headers = {}, apiBaseUrl = '') {
  return { ...headers, 'X-XSRF-TOKEN': await fetchCsrfToken(apiBaseUrl) };
}
