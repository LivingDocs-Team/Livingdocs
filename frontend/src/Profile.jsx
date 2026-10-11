
import { useState } from 'react';

function Profile() {
  const [name, setName] = useState('LivingDocs User');
  const [email, setEmail] = useState('user@example.com');
  const [message, setMessage] = useState('');

  function handleSubmit(event) {
    event.preventDefault();
    setMessage('Profile updated in this demo. Backend is not connected.');
  }

  return (
    <main className="page">
      <section className="login-card">
        <h1>User Profile</h1>
        <p className="subtitle">Manage your LivingDocs account</p>

        <form onSubmit={handleSubmit}>
          <label htmlFor="profile-name">Full name</label>
          <input
            id="profile-name"
            value={name}
            onChange={(event) => setName(event.target.value)}
            required
          />

          <label htmlFor="profile-email">Email</label>
          <input
            id="profile-email"
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            required
          />

          <button type="submit">Save changes</button>
        </form>

        {message && <p role="status">{message}</p>}
      </section>
    </main>
  );
}

export default Profile;