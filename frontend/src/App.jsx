
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

  function handleSubmit(event) {
    event.preventDefault();
    alert('Login UI demo only. Backend is not connected yet.');
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

                <button type="submit">Sign in</button>
              </form>

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
