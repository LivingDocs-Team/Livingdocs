
import { useEffect, useRef, useState } from 'react';
import './App.css';
import './theme.css';
import AnimatedBackground from './AnimatedBackground';
import AuthField from './AuthField';
import { csrfHeaders } from './csrf';
import Icon from './icons';
import PublicShell from './PublicShell';
import { useSpotlight } from './spotlight';

import Register from './Register';
import AppShell from './rbac/AppShell';
import { postLoginPath, resolveRoute } from './rbac/guard.js';
import { hrefFor, navigate, useHashPath } from './rbac/hashRoute.js';
import { RbacContext } from './rbac/usePermission.js';

const OAUTH_ERROR = new URLSearchParams(window.location.search).get('oauth') === 'error';

function App() {
  const hashPath = useHashPath();
  // { id, role, email } of the signed-in user, or null.
  const [user, setUser] = useState(null);
  const [isCheckingSession, setIsCheckingSession] = useState(true);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [isLoggingIn, setIsLoggingIn] = useState(false);
  const [loginError, setLoginError] = useState(() => (
    OAUTH_ERROR
      ? 'Could not sign in with GitHub. If your LivingDocs account already uses this email, sign in with your password and connect GitHub from GitHub Connection.'
      : ''
  ));
  const [loginSuccess, setLoginSuccess] = useState('');
  const [logoutError, setLogoutError] = useState('');
  // Internal page requested before sign-in; opened after sign-in when the role may access it.
  const requestedPath = useRef(null);

  useSpotlight();

  const path = hashPath || (OAUTH_ERROR ? '/login' : '/');
  const isAuthenticated = user != null;
  const decision = resolveRoute({ path, role: user?.role, isAuthenticated });

  useEffect(() => {
  let cancelled = false;

  async function restoreSession() {
    try {
      const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');

      const response = await fetch(apiBaseUrl + '/api/auth/me', {
        method: 'GET',
        credentials: 'include',
      });

      if (!response.ok) {
        sessionStorage.removeItem('livingdocs.userId');
        if (!cancelled) setUser(null);
        return;
      }

      const current = await response.json();

      if (!current || current.id == null) {
        throw new Error('Invalid current-user response');
      }

      if (!cancelled) {
        setUser({
          id: String(current.id),
          role: typeof current.role === 'string' ? current.role : '',
          email: typeof current.email === 'string' ? current.email : '',
        });
        sessionStorage.setItem('livingdocs.userId', String(current.id));
      }
    } catch {
      if (!cancelled) setUser(null);
    } finally {
      if (!cancelled) {
        setIsCheckingSession(false);
      }
    }
  }

  restoreSession();

  return () => {
    cancelled = true;
  };
}, []);
  useEffect(() => {
    // The route guard sends the now signed-out user from the internal page to Login.
    const handleSessionExpired = () => {
      sessionStorage.removeItem('livingdocs.userId');
      setUser(null);
      setLoginSuccess('');
      setLoginError('Your LivingDocs session has expired. Please sign in again.');
    };
    window.addEventListener('livingdocs:unauthenticated', handleSessionExpired);
    return () => window.removeEventListener('livingdocs:unauthenticated', handleSessionExpired);
  }, []);

  // Route guard redirects. Signed out on an internal URL -> Login (the URL is remembered). Signed in on
  // a public page (after password login, a restored session or GitHub OAuth) or an unknown URL -> the
  // remembered page when the role may open it, otherwise the role's landing page.
  useEffect(() => {
    if (isCheckingSession || decision.kind !== 'redirect') return;
    let target = decision.to;
    if (!isAuthenticated) {
      requestedPath.current = path;
    } else {
      target = postLoginPath(user.role, requestedPath.current) || target;
      requestedPath.current = null;
    }
    navigate(target, { replace: true });
  }, [isCheckingSession, decision.kind, decision.to, isAuthenticated, path, user]);

  async function handleSubmit(event) {
    event.preventDefault();
    if (isLoggingIn) return;

    setLoginError('');
    setLoginSuccess('');
    setIsLoggingIn(true);

    try {
      const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');
      const response = await fetch(apiBaseUrl + '/api/auth/login', {
        method: 'POST',
        headers: await csrfHeaders({ 'Content-Type': 'application/json' }, apiBaseUrl),
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
            ? (result?.message || 'Please enter a valid email and password.')
            : (result?.message || result?.detail || `Login failed (HTTP ${response.status}). Please try again.`);
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

      sessionStorage.setItem('livingdocs.userId', String(result.id));
      setUser({ id: String(result.id), role: result.role, email: result.email });
      setLoginSuccess('Signed in successfully as ' + result.email + '.');
    } catch {
      setLoginError('Could not connect to the backend. Check the backend URL and try again.');
    } finally {
      setIsLoggingIn(false);
    }
  }

  async function handleLogout() {
    setLogoutError('');
    try {
      const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');
      const response = await fetch(apiBaseUrl + '/api/auth/logout', {
        method: 'POST',
        credentials: 'include',
        headers: await csrfHeaders({}, apiBaseUrl),
        signal: AbortSignal.timeout(15000),
      });
      if (!response.ok && response.status !== 401) {
        setLogoutError('Could not sign out. Please retry.');
        return;
      }
      sessionStorage.removeItem('livingdocs.userId');
      navigate('/');
      setUser(null);
      setLoginSuccess('');
    } catch {
      setLogoutError('Could not connect to the backend to end the session.');
    }
  }

  const renderPublicCard = (page) => {
    switch (page) {
      case 'register':
        return (
          <>
            <Register />
            <p className="auth-foot">
              Already have an account?{' '}
              <button className="text-button" type="button" onClick={() => navigate('/login')}>
                Sign in
              </button>
            </p>
          </>
        );

      case 'home':
        return (
          <section aria-labelledby="home-title">
            <div className="auth-icon"><Icon name="term" size={17} /></div>
            <h2 id="home-title">Get started</h2>
            <p className="auth-sub">AI-assisted, self-updating documentation for engineering teams.</p>
            <div className="auth-actions">
              <a className="auth-submit" href={hrefFor('/login')}>Sign in<Icon name="arrow" /></a>
              <a className="auth-secondary" href={hrefFor('/register')}>Create a Developer account</a>
            </div>
          </section>
        );

      case 'login':
      default:
        return (
          <section aria-labelledby="login-title">
            <div className="auth-icon"><Icon name="term" size={17} /></div>
            <h2 id="login-title">Sign in to your account</h2>
            <p className="auth-sub">Welcome back. Pick up where you left off.</p>

            <form onSubmit={handleSubmit}>
              <AuthField
                id="email"
                label="Email"
                icon="mail"
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="you@company.com"
                required
              />
              <AuthField
                id="password"
                label="Password"
                icon="lock"
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder="Enter your password"
                required
              />
              <button className="auth-submit" type="submit" disabled={isLoggingIn}>
                {isLoggingIn ? 'Signing in...' : 'Sign in'}
                <Icon name="arrow" />
              </button>
            </form>
            {loginError && <p className="auth-message" role="alert">{loginError}</p>}

            <div className="separator">or</div>

            <button
              className="github-button"
              type="button"
              onClick={() => window.location.assign(
                `${(import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')}/oauth2/authorization/github`,
              )}
            >
              <Icon name="github" />
              Continue with GitHub
            </button>

            <p className="auth-foot">
              Don't have an account?{' '}
              <button className="text-button" type="button" onClick={() => navigate('/register')}>
                Sign up
              </button>
              {' '}(Developer accounts only)
            </p>
          </section>
        );
    }
  };

  if (isCheckingSession) {
    return (
      <>
        <AnimatedBackground />
        <div className="app-content session-check">Checking session...</div>
      </>
    );
  }

  if (!isAuthenticated) {
    const page = decision.kind === 'public' ? decision.page : null;
    return (
      <>
        <AnimatedBackground />
        {page
          ? <PublicShell key={page} page={page}>{renderPublicCard(page)}</PublicShell>
          : <p className="session-check" role="status">Redirecting…</p>}
      </>
    );
  }

  return (
    <RbacContext.Provider value={user.role}>
      <AnimatedBackground />
      <AppShell
        decision={decision}
        userId={user.id}
        userRole={user.role}
        userEmail={user.email}
        notice={loginSuccess}
        onLogout={handleLogout}
        logoutError={logoutError}
      />
    </RbacContext.Provider>
  );
}

export default App;
