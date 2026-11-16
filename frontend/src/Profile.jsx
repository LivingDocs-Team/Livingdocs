import { useEffect, useState } from 'react';
import { githubApi } from './githubApi';

// LD-49 / LD-50: profile of the signed-in user (Backend GET / PATCH /api/profile).
function Profile() {
  const [profile, setProfile] = useState(null);
  const [form, setForm] = useState({ username: '', firstName: '', lastName: '' });
  const [isSaving, setIsSaving] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    githubApi('/api/profile')
      .then((data) => {
        if (cancelled) return;
        setProfile(data);
        setForm({ username: data.username || '', firstName: data.firstName || '', lastName: data.lastName || '' });
      })
      .catch((requestError) => {
        if (!cancelled) setError(requestError.message || 'Could not load your profile.');
      });
    return () => {
      cancelled = true;
    };
  }, []);

  function handleChange(event) {
    const { name, value } = event.target;
    setForm((previous) => ({ ...previous, [name]: value }));
    setMessage('');
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setIsSaving(true);
    setMessage('');
    setError('');
    try {
      const saved = await githubApi('/api/profile', { method: 'PATCH', body: form });
      setProfile(saved);
      setMessage('Profile saved.');
    } catch (requestError) {
      setError(requestError.message || 'Could not save your profile.');
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <main className="page">
      <section className="login-card">
        <h1>User Profile</h1>
        <p className="subtitle">Manage your LivingDocs account</p>

        {!profile && !error && <p role="status">Loading your profile…</p>}
        {profile && (
          <form onSubmit={handleSubmit}>
            <label htmlFor="profile-username">Username</label>
            <input id="profile-username" name="username" value={form.username}
              onChange={handleChange} maxLength={50} required />

            <label htmlFor="profile-first-name">First name</label>
            <input id="profile-first-name" name="firstName" value={form.firstName}
              onChange={handleChange} maxLength={100} required />

            <label htmlFor="profile-last-name">Last name</label>
            <input id="profile-last-name" name="lastName" value={form.lastName}
              onChange={handleChange} maxLength={100} required />

            <label htmlFor="profile-email">Email</label>
            <input id="profile-email" type="email" value={profile.email} readOnly aria-describedby="profile-email-hint" />
            <p id="profile-email-hint" className="subtitle">
              Email is your sign-in name and cannot be changed here. Role: {profile.role}
            </p>

            <button type="submit" disabled={isSaving}>{isSaving ? 'Saving…' : 'Save changes'}</button>
          </form>
        )}

        {message && <p role="status">{message}</p>}
        {error && <p className="sync-error" role="alert">{error}</p>}
      </section>
    </main>
  );
}

export default Profile;
