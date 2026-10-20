
import { useState } from 'react';
import './App.css';

import Register from './Register';
import Profile from './Profile';
import NotificationPreferences from './NotificationPreferences';
import GitHubConnection from './GitHubConnection';
import RepositoryManagement from './RepositoryManagement';
import DocumentationManagement from './DocumentationManagement';

function App() {
  const [page, setPage] = useState('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [isLoggingIn, setIsLoggingIn] = useState(false);
  const [loginError, setLoginError] = useState('');
  const [loginSuccess, setLoginSuccess] = useState('');

  async function handleSubmit(event) {
    event.preventDefault();
    if (isLoggingIn) return;

    setLoginError('');
    setLoginSuccess('');
    setIsLoggingIn(true);

    try {
      const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8080')
        .replace(/\/$/, '');
      const response = await fetch(apiBaseUrl + '/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ email, password }),
      });

      let result = null;
      try {
        result = await response.json();
      } catch {
        // An empty or invalid response body is handled below.
      }

      if (!response.ok) {
        const errorMessage = response.status === 401
          ? 'Invalid email or password.'
          : response.status === 400
            ? 'Please enter a valid email and password.'
            : 'Login failed. Please try again.';
        setLoginError(errorMessage);
        return;
      }

      const hasValidResponse = result
        && typeof result === 'object'
        && !Array.isArray(result)
        && typeof result.id === 'number'
        && ['message', 'email', 'username', 'firstName', 'lastName', 'role']
          .every((field) => typeof result[field] === 'string');

      if (!hasValidResponse) {
        setLoginError('The backend returned an invalid login response.');
        return;
      }

      setLoginSuccess('Signed in successfully as ' + result.email + '.');
    } catch {
      setLoginError('Could not connect to the backend. Check the backend URL and try again.');
    } finally {
      setIsLoggingIn(false);
    }
  }

  const renderPage = () => {
    switch (page) {
      case 'register':
        return (
          <>
            <Register />
            <p className="switch-page">
              Already have an account?{' '}
              <button type="button" onClick={() => setPage('login')}>
                Sign in
              </button>
            </p>
          </>
        );

      case 'profile':
        return (
          <>
            <Profile />
            <p className="switch-page">
              <button type="button" onClick={() => setPage('login')}>
                Back to login
              </button>
            </p>
          </>
        );

      case 'notifications':
        return (
          <>
            <NotificationPreferences />
            <p className="switch-page">
              <button type="button" onClick={() => setPage('login')}>
                Back to login
              </button>
            </p>
          </>
        );

      case 'github':
        return (
          <>
            <GitHubConnection />
            <p className="switch-page">
              <button type="button" onClick={() => setPage('login')}>
                Back to login
              </button>
            </p>
          </>
        );

      case 'repository':
        return (
          <>
            <RepositoryManagement />
            <p className="switch-page">
              <button type="button" onClick={() => setPage('login')}>
                Back to login
              </button>
            </p>
          </>
        );

      case 'documentation':
        return (
          <>
            <DocumentationManagement />
            <p className="switch-page">
              <button type="button" onClick={() => setPage('login')}>
                Back to login
              </button>
            </p>
          </>
        );

      case 'login':
      default:
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

                <button type="submit" disabled={isLoggingIn}>
                  {isLoggingIn ? 'Signing in...' : 'Sign in'}
                </button>
              </form>
              {loginError && <p role="alert">{loginError}</p>}
              {loginSuccess && <p role="status">{loginSuccess}</p>}

              <div className="separator">or</div>

              <button
                className="github-button"
                type="button"
                onClick={() => setPage('github')}
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

            <section className="quick-access">
              <h2>Quick access</h2>
              <p className="quick-access-description">
                Access your development tools directly from LivingDocs.
              </p>

              <div className="quick-access-grid">
                <button
                  className="quick-access-card"
                  type="button"
                  onClick={() => setPage('github')}
                >
                  <span className="quick-access-icon" aria-hidden="true">
                    {'</>'}
                  </span>
                  <span className="quick-access-title">
                    GitHub Connection
                  </span>
                  <span className="quick-access-description">
                    Connect and manage your GitHub account.
                  </span>
                  <span className="quick-access-link">Open feature →</span>
                </button>

                <button
                  className="quick-access-card"
                  type="button"
                  onClick={() => setPage('repository')}
                >
                  <span className="quick-access-icon" aria-hidden="true">
                    {'{ }'}
                  </span>
                  <span className="quick-access-title">
                    Repository Management
                  </span>
                  <span className="quick-access-description">
                    View and manage your repositories.
                  </span>
                  <span className="quick-access-link">Open feature →</span>
                </button>

                <button
                  className="quick-access-card"
                  type="button"
                  onClick={() => setPage('documentation')}
                >
                  <span className="quick-access-icon" aria-hidden="true">
                    {'▤'}
                  </span>
                  <span className="quick-access-title">
                    Documentation Management
                  </span>
                  <span className="quick-access-description">
                    Create and manage project documentation.
                  </span>
                  <span className="quick-access-link">Open feature →</span>
                </button>
              </div>
            </section>
          </main>
        );
    }
  };

  return (
    <div className="app">
      {page !== 'login' && (
        <nav className="app-navigation">
          <div className="nav-brand">LivingDocs</div>

          <div className="nav-links">
            <button type="button" onClick={() => setPage('github')}>
              GitHub Connection
            </button>

            <button type="button" onClick={() => setPage('repository')}>
              Repository Management
            </button>

            <button type="button" onClick={() => setPage('documentation')}>
              Documentation Management
            </button>

            <button type="button" onClick={() => setPage('profile')}>
              Profile
            </button>

            <button type="button" onClick={() => setPage('notifications')}>
              Notifications
            </button>

            <button type="button" onClick={() => setPage('login')}>
              Logout
            </button>
          </div>
        </nav>
      )}

      <main className="app-content">{renderPage()}</main>
    </div>
  );
}

export default App;
