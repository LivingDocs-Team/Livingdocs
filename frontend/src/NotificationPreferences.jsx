import { useEffect, useState } from 'react';
import { githubApi } from './githubApi';

// LD-51: notification preferences of the signed-in user (Backend GET / PUT /api/profile/notification-preferences).
const PREFERENCES = [
  ['emailUpdates', 'Email updates'],
  ['documentChanges', 'Document changes'],
  ['reviewRequests', 'Review requests'],
  ['systemNotifications', 'System notifications'],
];

function NotificationPreferences() {
  const [preferences, setPreferences] = useState(null);
  const [isSaving, setIsSaving] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    githubApi('/api/profile/notification-preferences')
      .then((data) => {
        if (!cancelled) setPreferences(data);
      })
      .catch((requestError) => {
        if (!cancelled) setError(requestError.message || 'Could not load your notification preferences.');
      });
    return () => {
      cancelled = true;
    };
  }, []);

  function handleChange(event) {
    const { name, checked } = event.target;
    setPreferences((previous) => ({ ...previous, [name]: checked }));
    setMessage('');
  }

  async function handleSave(event) {
    event.preventDefault();
    setIsSaving(true);
    setMessage('');
    setError('');
    try {
      setPreferences(await githubApi('/api/profile/notification-preferences', { method: 'PUT', body: preferences }));
      setMessage('Preferences saved.');
    } catch (requestError) {
      setError(requestError.message || 'Could not save your notification preferences.');
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <main className="page">
      <section className="login-card">
        <h1>Notification Preferences</h1>
        <p className="subtitle">
          Choose which notifications you want to receive.
        </p>

        {!preferences && !error && <p role="status">Loading your preferences…</p>}
        {preferences && (
          <form onSubmit={handleSave}>
            {PREFERENCES.map(([name, label]) => (
              <label className="preference" key={name}>
                <input type="checkbox" name={name} checked={Boolean(preferences[name])} onChange={handleChange} />
                {label}
              </label>
            ))}

            <button type="submit" disabled={isSaving}>{isSaving ? 'Saving…' : 'Save preferences'}</button>
          </form>
        )}

        {message && <p role="status">{message}</p>}
        {error && <p className="sync-error" role="alert">{error}</p>}
      </section>
    </main>
  );
}

export default NotificationPreferences;
