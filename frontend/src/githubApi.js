import { csrfHeaders } from './csrf';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '';

const ERROR_MESSAGES = {
  NOT_FOUND: 'The requested resource was not found.',
  BAD_REQUEST: 'The request could not be completed. Check the submitted information and try again.',
  FORBIDDEN: 'You do not have permission to perform this action.',
  GITHUB_ACCESS_DENIED: 'GitHub access was denied. Please authorize LivingDocs and try again.',
  GITHUB_NOT_CONNECTED: 'Connect your GitHub account before continuing.',
  GITHUB_REAUTH_REQUIRED: 'Your GitHub authorization expired. Reconnect your GitHub account and try again.',
  TOKEN_INVALID: 'Your GitHub authorization is invalid. Reconnect your GitHub account and try again.',
  ACCESS_DENIED: 'GitHub denied access to this repository. Check the GitHub App permissions and repository installation.',
  REPOSITORY_NOT_FOUND: 'This repository is unavailable. Check that it still exists and that the GitHub App can access it.',
  BRANCH_NOT_FOUND: 'The requested repository branch was not found. Check the branch name and try again.',
  EMPTY_REPOSITORY: 'This repository has no commits to synchronize yet. Add a commit and try again.',
  INVALID_REQUEST: 'The sync request is invalid. Review the repository and sync options, then try again.',
  INVALID_REPOSITORY: 'The repository identifier is invalid. Refresh the repository list and try again.',
  RATE_LIMITED: 'GitHub rate limit reached. Wait before trying again.',
  GITHUB_UNAVAILABLE: 'GitHub is temporarily unavailable. Wait a moment and retry.',
  UNEXPECTED_GITHUB_RESPONSE: 'GitHub returned an unexpected response. Try again later.',
  TEMPLATE_NOT_FOUND: 'The selected documentation template was not found. Choose another template and try again.',
  TEMPLATE_READ_ONLY: 'Built-in documentation templates cannot be edited.',
  TEMPLATE_NAME_TAKEN: 'A documentation template with that name already exists.',
  TEMPLATE_INVALID: 'The documentation template is invalid. Review its name, instructions, and sections.',
  GENERATION_REQUEST_INVALID: 'The documentation generation request is invalid. Check the selected repository and template.',
  DOCUMENTATION_NOT_READY: 'Documentation is not ready yet. Wait for generation to finish and try again.',
  AI_SERVICE_FAILED: 'The documentation service is temporarily unavailable. Try again later.',
  AI_SERVICE_INVALID_RESPONSE: 'The documentation service returned an invalid response. Try again later.',
};

function isVietnameseMessage(message) {
  return /[ăâđêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ]/i.test(message)
    || /\b(khong|loi|that bai|ket noi|yeu cau|vui long|xac thuc|khong the)\b/i.test(message);
}

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
    const code = !text && data && typeof data.code === 'string' ? data.code : undefined;
    const backendMessage = !text && data && typeof data.message === 'string' ? data.message : '';
    const message = ERROR_MESSAGES[code]
      || (backendMessage && !isVietnameseMessage(backendMessage) ? backendMessage : '')
      || `Request failed (HTTP ${response.status}).`;
    const error = new Error(message);
    error.status = response.status;
    error.code = code;
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
