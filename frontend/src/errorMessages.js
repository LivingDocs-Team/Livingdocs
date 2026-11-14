// L15: the interface is in English, but the GitHub Integration Service returns some
// messages in Vietnamese. Show a fixed English message for each stable error code
// instead of the service text. For other codes the service message is kept only
// when it is plain English text; otherwise a general message for the HTTP status is used.

const MESSAGES_BY_CODE = {
  // GitHub connection
  GITHUB_NOT_CONNECTED: 'GitHub is not connected. Connect GitHub and try again.',
  GITHUB_REAUTH_REQUIRED: 'GitHub authorization expired. Reconnect GitHub.',
  GITHUB_ACCESS_DENIED: 'GitHub access was not granted. Authorize GitHub again to connect.',
  GITHUB_API_ERROR: 'GitHub did not respond as expected. Please try again later.',
  INTERNAL_SERVICE_AUTH_REQUIRED: 'LivingDocs could not reach the GitHub integration service. Please try again later.',
  INTERNAL_ERROR: 'The GitHub integration service had an unexpected error. Please try again later.',
  VALIDATION_ERROR: 'Select at least one repository.',
  // Repository synchronization
  INVALID_REQUEST: 'The sync options are not valid.',
  INVALID_REPOSITORY: 'The repository name is not valid.',
  TOKEN_INVALID: 'GitHub authorization expired. Reconnect GitHub, then sync again.',
  ACCESS_DENIED: 'The GitHub App cannot read this repository. Give the app access to it on GitHub, then sync again.',
  REPOSITORY_NOT_FOUND: 'The repository was not found on GitHub. It may have been deleted or renamed, or the GitHub App has no access to it.',
  BRANCH_NOT_FOUND: 'The branch was not found in this repository.',
  EMPTY_REPOSITORY: 'This repository has no commits yet, so there is nothing to sync.',
  RATE_LIMITED: 'GitHub rate limit reached. Please try again later.',
  GITHUB_UNAVAILABLE: 'GitHub is unavailable right now. Please try again later.',
  UNEXPECTED_GITHUB_RESPONSE: 'GitHub returned an unexpected response. Please try again later.',
  // Documentation templates and generation (messages from LD-101, PR #69)
  TEMPLATE_NOT_FOUND: 'The selected documentation template was not found. Choose another template and try again.',
  TEMPLATE_READ_ONLY: 'Built-in documentation templates cannot be edited.',
  TEMPLATE_NAME_TAKEN: 'A documentation template with that name already exists.',
  TEMPLATE_INVALID: 'The documentation template is invalid. Review its name, instructions, and sections.',
  GENERATION_REQUEST_INVALID: 'The documentation generation request is invalid. Check the selected repository and template.',
  DOCUMENTATION_NOT_READY: 'Documentation is not ready yet. Wait for generation to finish and try again.',
  AI_SERVICE_FAILED: 'The documentation service is temporarily unavailable. Try again later.',
  AI_SERVICE_INVALID_RESPONSE: 'The documentation service returned an invalid response. Try again later.',
  // Documentation drift (LD-145, LD-156)
  PULL_REQUEST_NOT_FOUND: 'The pull request was not found in this repository. Check the number and try again.',
  DRIFT_REQUEST_INVALID: 'The pull request could not be checked for documentation drift.',
  GITHUB_INVALID_RESPONSE: 'GitHub returned an incomplete pull request. Please try again later.',
};

const MESSAGES_BY_STATUS = {
  400: 'The request is not valid.',
  403: 'You do not have access to this item.',
  404: 'The requested item was not found.',
  409: 'The request could not be completed in the current state. Refresh the page and try again.',
};

// Characters outside plain ASCII mean the text is not English (for example Vietnamese).
const NON_ENGLISH = /[^\t\n\r\x20-\x7E]/;
// Vietnamese written without accents (check kept from LD-101, PR #69).
const UNACCENTED_VIETNAMESE = /\b(khong|loi|that bai|ket noi|yeu cau|vui long|xac thuc|khong the)\b/i;

function isEnglish(message) {
  return !NON_ENGLISH.test(message) && !UNACCENTED_VIETNAMESE.test(message);
}

export function apiErrorMessage(code, status, serviceMessage) {
  if (code && MESSAGES_BY_CODE[code]) {
    return MESSAGES_BY_CODE[code];
  }
  if (typeof serviceMessage === 'string' && serviceMessage.trim() && isEnglish(serviceMessage)) {
    return serviceMessage;
  }
  return MESSAGES_BY_STATUS[status] || `Request failed (HTTP ${status}).`;
}

// Reasons sent back by the GitHub callback (?github=error&reason=<code>).
export function gitHubConnectErrorMessage(reason) {
  if (reason === 'BAD_REQUEST') {
    return 'GitHub connection failed: the connection request was not valid or has expired. Authorize GitHub again.';
  }
  return `GitHub connection failed: ${MESSAGES_BY_CODE[reason] || 'unknown error. Please try again.'}`;
}



