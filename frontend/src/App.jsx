
import { useState } from 'react';
import './App.css';
import Register from './Register';
import Profile from './Profile';
import NotificationPreferences from './NotificationPreferences';

function App() {
  const [page, setPage] = useState('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');

  if (page === 'register') {
    return (
      <>
        <Register />
        <p className="switch-page">
          Already have an account?{' '}
          <button onClick={() => setPage('login')}>
            Sign in
          </button>
        </p>
      </>
    );
  }

  if (page === 'profile') {
    return (
      <>
        <Profile />
        <p className="switch-page">
          <button onClick={() => setPage('login')}>
            Back to login
          </button>
        </p>
      </>
    );
  }

  if (page === 'notifications') {
    return (
      <>
        <NotificationPreferences />
        <p className="switch-page">
          <button onClick={() => setPage('login')}>
            Back to login
          </button>
        </p>
      </>
    );
  }

  function handleSubmit(event) {
    event.preventDefault();
    alert('Login UI demo only. Backend is not connected.');
  }

  return (
    <main className="page">
      <section className="login-card">
        <h1>LivingDocs</h1>
        <p className="subtitle">Sign in to your account</p>

        <form onSubmit={handleSubmit}>
          <label htmlFor="email">Email</label>
          <input
            id="email"
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            required
          />

          <label htmlFor="password">Password</label>
          <input
            id="password"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
          />

          <button type="submit">Sign in</button>
        </form>

        <div className="separator">or</div>

        <button
          className="github-button"
          type="button"
          onClick={() => alert('GitHub OAuth is not connected yet.')}
        >
          Continue with GitHub
        </button>

        <p className="footer">
          Don't have an account?{' '}
          <button
            className="text-button"
            type="button"
            onClick={() => setPage('register')}
          >
            Sign up
          </button>
        </p>

        <p className="footer">
          <button
            className="text-button"
            type="button"
            onClick={() => setPage('profile')}
          >
            View demo profile
          </button>
        </p>

        <p className="footer">
          <button
            className="text-button"
            type="button"
            onClick={() => setPage('notifications')}
          >
            Notification preferences
          </button>
        </p>
      </section>
    </main>
  );
}

export default App;