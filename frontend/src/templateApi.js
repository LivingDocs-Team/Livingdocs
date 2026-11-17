import { useCallback, useEffect, useState } from 'react';
import { githubApi } from './githubApi';

const BASE = '/api/documentation/templates';

/** Sections a template can contain, in the spelling the API accepts. */
export const SECTION_NAMES = ['Overview', 'Classes', 'Functions', 'API Endpoints'];

export const SECTION_HINTS = {
  Overview: 'Purpose of each file',
  Classes: 'Classes and their methods',
  Functions: 'Module-level functions',
  'API Endpoints': 'HTTP endpoints',
};

/** Shown when the template list cannot be loaded; same ids as the AI service built-ins. */
export const FALLBACK_TEMPLATES = [
  {
    id: 'default',
    name: 'Standard technical docs',
    description: 'Overview, classes, functions and API endpoints.',
    instructions: 'Explain the purpose, parameters and return value of every class, method, function and endpoint.',
    sections: ['Overview', 'Classes', 'Functions', 'API Endpoints'],
    built_in: true,
  },
  {
    id: 'api-reference',
    name: 'API reference',
    description: 'Focus on HTTP endpoints: parameters, request and response.',
    instructions: 'Document only the public API: method, path, purpose, parameters, request and response.',
    sections: ['Overview', 'API Endpoints'],
    built_in: true,
  },
  {
    id: 'brief',
    name: 'Brief summary',
    description: 'Short summary for code review or onboarding.',
    instructions: 'Write a concise summary: at most two sentences per item.',
    sections: ['Overview', 'Classes', 'Functions'],
    built_in: true,
  },
];

export function createTemplate(template) {
  return githubApi(BASE, { method: 'POST', body: template });
}

export function updateTemplate(id, template) {
  return githubApi(`${BASE}/${encodeURIComponent(id)}`, { method: 'PUT', body: template });
}

export function deleteTemplate(id) {
  return githubApi(`${BASE}/${encodeURIComponent(id)}`, { method: 'DELETE' });
}

/** Available templates for a signed-in user; falls back to the built-in list on failure. */
export function useTemplates(userId) {
  const [state, setState] = useState({
    templates: FALLBACK_TEMPLATES,
    isLoading: Boolean(userId),
    loadError: '',
  });
  const [version, setVersion] = useState(0);

  useEffect(() => {
    if (!userId) return undefined;
    let cancelled = false;
    githubApi(BASE)
      .then((items) => {
        if (cancelled) return;
        setState({
          templates: Array.isArray(items) && items.length ? items : FALLBACK_TEMPLATES,
          isLoading: false,
          loadError: '',
        });
      })
      .catch(() => {
        if (cancelled) return;
        setState({
          templates: FALLBACK_TEMPLATES,
          isLoading: false,
          loadError: 'Could not load templates from the server. Showing the built-in templates.',
        });
      });
    return () => { cancelled = true; };
  }, [userId, version]);

  const reload = useCallback(() => setVersion((value) => value + 1), []);
  return { ...state, reload };
}
