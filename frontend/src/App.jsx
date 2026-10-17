
import { useState } from 'react';
import './App.css';

import Register from './Register';
import Profile from './Profile';
import NotificationPreferences from './NotificationPreferences';
import GitHubConnection from './github/GitHubConnection';
import RepositoryManagement from './RepositoryManagement';
import DocumentationManagement from './DocumentationManagement';

function App() {
  const [page, setPage] = useState('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');

  function handleSubmit(event) {
    event.preventDefault();
    alert('Login UI demo only. Backend is not connected.');
  }

  // Trang đăng ký
  if (page === 'register') {
    return (
      <>
        <Register />

        <p className="switch-page">
          Already have an account?{' '}
          <button
            type="button"
            onClick={() => setPage('login')}
          >
            Sign in
          </button>
        </p>
      </>
    );
  }

  // Trang hồ sơ
  if (page === 'profile') {
    return (
      <>
        <Profile />

        <p className="switch-page">
          <button
            type="button"
            onClick={() => setPage('login')}
          >
            Back to login
          </button>
        </p>
      </>
    );
  }

  // Trang cài đặt thông báo
  if (page === 'notifications') {
    return (
      <>
        <NotificationPreferences />

        <p className="switch-page">
          <button
            type="button"
            onClick={() => setPage('login')}
          >
            Back to login
          </button>
        </p>
      </>
    );
  }

  // Trang kết nối GitHub
  if (page === 'github') {
    return (
      <>
        <GitHubConnection />

        <p className="switch-page">
          <button
            type="button"
            onClick={() => setPage('login')}
          >
            Back to login
          </button>
        </p>
      </>
    );
  }

  // Trang quản lý repositories
  if (page === 'repositories') {
    return (
      <>
        <RepositoryManagement />

        <p className="switch-page">
          <button
            type="button"
            onClick={() => setPage('login')}
          >
            Back to login
          </button>
        </p>
      </>
    );
  }

  // Trang quản lý tài liệu
  if (page === 'documentation') {
    return (
      <>
        <DocumentationManagement />

        <p className="switch-page">
          <button
            type="button"
            onClick={() => setPage('login')}
          >
            Back to login
          </button>
        </p>
      </>
    );
  }

  // Trang đăng nhập mặc định
  return (
    <main className="page">
      <section className="login-card">
        <h1>LivingDocs</h1>

        <p className="subtitle">
          Sign in to your account
        </p>

        <form onSubmit={handleSubmit}>
          <label htmlFor="email">
            Email
          </label>

          <input
            id="email"
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            autoComplete="email"
            required
          />

          <label htmlFor="password">
            Password
          </label>

          <input
            id="password"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete="current-password"
            required
          />

          <button type="submit">
            Sign in
          </button>
        </form>

        <div className="separator">
          or
        </div>

        <button
          className="github-button"
          type="button"
          onClick={() =>
            alert('GitHub OAuth is not connected yet.')
          }
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

        <p className="footer">
          <button
            className="text-button"
            type="button"
            onClick={() => setPage('github')}
          >
            GitHub connection
          </button>
        </p>

        <p className="footer">
          <button
            className="text-button"
            type="button"
            onClick={() => setPage('repositories')}
          >
            Repository Management
          </button>
        </p>

        <p className="footer">
          <button
            className="text-button"
            type="button"
            onClick={() => setPage('documentation')}
          >
            Documentation Management
          </button>
        </p>
      </section>
    </main>
  );
}

export default App;
