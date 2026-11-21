import React, { useEffect, useState } from 'react';

interface ChangeLogEntry {
  id: string;
  documentId: string;
  eventType: string;
  actorName: string;
  summary: string;
  occurredAt: string;
}

export default function ChangeLogTimeline({ documentId }: { documentId: string }) {
  const [entries, setEntries] = useState<ChangeLogEntry[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!documentId) return;
    setLoading(true);
    setError(null);
    fetch(`/api/documentation/${documentId}/change-log`)
      .then((res) => {
        if (res.status === 403 || res.status === 404) {
          throw new Error('PERMISSION_DENIED');
        }
        if (!res.ok) throw new Error('FETCH_ERROR');
        return res.json();
      })
      .then((data: ChangeLogEntry[]) => {
        setEntries(data);
        setLoading(false);
      })
      .catch((err) => {
        if (err.message === 'PERMISSION_DENIED') {
          setError('Bạn không có quyền xem lịch sử thay đổi của tài liệu này.');
        } else {
          setError('Không tải được lịch sử thay đổi.');
        }
        setLoading(false);
      });
  }, [documentId]);

  return (
    <section style={{ borderLeft: '2px solid #ddd', paddingLeft: '1rem' }}>
      <h3>Lịch sử thay đổi tài liệu</h3>
      {loading && <p>Đang tải…</p>}
      {error && <p style={{ color: 'red' }}>{error}</p>}
      
      {!loading && !error && entries.length > 0 && (
        <ol style={{ listStyle: 'none', padding: 0 }}>
          {entries.map((entry) => (
            <li key={entry.id} style={{ marginBottom: '1rem', position: 'relative' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.9rem' }}>
                <strong>{entry.actorName}</strong>
                <time>{new Date(entry.occurredAt).toLocaleString()}</time>
              </div>
              <p style={{ margin: '0.2rem 0' }}>{entry.summary}</p>
              <small style={{ background: '#eee', padding: '0 0.4rem', borderRadius: '4px' }}>
                {entry.eventType}
              </small>
            </li>
          ))}
        </ol>
      )}
      {!loading && !error && entries.length === 0 && <p>Chưa có thay đổi nào.</p>}
    </section>
  );
}