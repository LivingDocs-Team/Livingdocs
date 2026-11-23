import { useEffect, useState } from 'react';
import { githubApi } from './githubApi';

const PAGE_SIZE = 50;

/**
 * The workflows the signed-in user may read (history-accessible), one page at a time, with the selected one.
 * `filter` keeps only some of them (for example one status group); the selection follows the filtered list.
 */
export default function useWorkflowList(userId, filter) {
  const [pageIndex, setPageIndex] = useState(0);
  const [reload, setReload] = useState(0);
  const [selectedId, setSelectedId] = useState('');
  const [state, setState] = useState({ key: '', page: null, error: '' });
  const key = `${userId}:${pageIndex}:${reload}`;

  useEffect(() => {
    if (!userId) return undefined;
    let cancelled = false;
    githubApi(`/api/document-workflows/history-accessible?page=${pageIndex}&size=${PAGE_SIZE}`, { userId })
      .then((page) => {
        if (cancelled) return;
        if (!page || !Array.isArray(page.content)) throw new Error('The workflow list was not valid.');
        setState({ key, page, error: '' });
      })
      .catch((error) => {
        if (!cancelled) setState({ key, page: null, error: error.message || 'Could not load the workflows.' });
      });
    return () => { cancelled = true; };
  }, [userId, pageIndex, key]);

  const ready = state.key === key;
  const all = ready ? state.page?.content || [] : [];
  const workflows = filter ? all.filter(filter) : all;
  const selected = workflows.find((item) => item.id === selectedId) || workflows[0] || null;

  return {
    ready, error: ready ? state.error : '', page: ready ? state.page : null, workflows, all,
    selected, selectedId: selected?.id || '', select: setSelectedId,
    pageIndex, setPageIndex, retry: () => setReload((value) => value + 1),
  };
}
