
import { useState } from 'react';

function NotificationPreferences() {
  const [preferences, setPreferences] = useState({
    emailUpdates: true,
    documentChanges: true,
    reviewRequests: true,
    systemNotifications: true,
  });

  const [message, setMessage] = useState('');

  function handleChange(event) {
    const { name, checked } = event.target;

    setPreferences((previous) => ({
      ...previous,
      [name]: checked,
    }));

    setMessage('');
  }

  function handleSave(event) {
    event.preventDefault();
    setMessage('Preferences saved successfully! (Demo only)');
  }

  return (
    <main className="page">
      <section className="login-card">
        <h1>Notification Preferences</h1>
        <p className="subtitle">
          Choose which notifications you want to receive.
        </p>

        <form onSubmit={handleSave}>
          <label className="preference">
            <input
              type="checkbox"
              name="emailUpdates"
              checked={preferences.emailUpdates}
              onChange={handleChange}
            />
            Email updates
          </label>

          <label className="preference">
            <input
              type="checkbox"
              name="documentChanges"
              checked={preferences.documentChanges}
              onChange={handleChange}
            />
            Document changes
          </label>

          <label className="preference">
            <input
              type="checkbox"
              name="reviewRequests"
              checked={preferences.reviewRequests}
              onChange={handleChange}
            />
            Review requests
          </label>

          <label className="preference">
            <input
              type="checkbox"
              name="systemNotifications"
              checked={preferences.systemNotifications}
              onChange={handleChange}
            />
            System notifications
          </label>

          <button type="submit">Save preferences</button>
        </form>

        {message && <p role="status">{message}</p>}
      </section>
    </main>
  );
}

export default NotificationPreferences;