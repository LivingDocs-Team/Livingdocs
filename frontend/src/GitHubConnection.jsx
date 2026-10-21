import { useEffect, useState } from 'react';
import { githubApi } from './githubApi';

function GitHubConnection({ userId }) {
  const [connection, setConnection] = useState(null);
  const [isLoading, setIsLoading] = useState(Boolean(userId));
  const [isConnecting, setIsConnecting] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get('github') === 'connected') {
      setNotice(`GitHub connected${params.get('login') ? ` as @${params.get('login')}` : ''}.`);
      window.history.replaceState({}, document.title, window.location.pathname);
    } else if (params.get('github') === 'error') {
      setError(`GitHub connection failed (${params.get('reason') || 'unknown error'}).`);
      window.history.replaceState({}, document.title, window.location.pathname);
    }

    if (!userId) {
      setConnection(null);
      setIsLoading(false);
      return;
    }

    let cancelled = false;
    setIsLoading(true);
    githubApi('/api/github/connection', { userId })
      .then((result) => {
        if (!cancelled) setConnection(result);
      })
      .catch((requestError) => {
        if (!cancelled) setError(requestError.message);
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    return () => { cancelled = true; };
  }, [userId]);

  async function handleConnect(useInstallationUrl = false) {
    setError('');
    setNotice('');
    setIsConnecting(true);
    try {
      const urls = await githubApi('/api/github/authorize-url', { userId });
      const url = useInstallationUrl ? urls.installUrl : urls.authorizeUrl;
      if (!url) throw new Error('GitHub did not return an authorization URL.');
      window.location.assign(url);
    } catch (requestError) {
      setError(requestError.message || 'Could not start GitHub authorization.');
      setIsConnecting(false);
    }
  }

  async function handleDisconnect() {
    setError('');
    setNotice('');
    setIsLoading(true);
    try {
      await githubApi('/api/github/connection', { method: 'DELETE', userId });
      setConnection({ connected: false, status: 'REVOKED' });
      setNotice('GitHub disconnected.');
    } catch (requestError) {
      setError(requestError.message || 'Could not disconnect GitHub.');
    } finally {
      setIsLoading(false);
    }
  }

  const isConnected = Boolean(connection?.connected);

  return (
    <main className="page">
      <section className="login-card github-connection-card">
        <h1>GitHub Integration</h1>
        <p className="subtitle">Connect your GitHub account to manage repositories in LivingDocs.</p>

        {!userId && <p role="alert">Sign in to LivingDocs before connecting GitHub.</p>}
        {isLoading && <p role="status">Loading GitHub connection…</p>}
        {error && <p role="alert">{error}</p>}
        {notice && <p role="status">{notice}</p>}

        {userId && !isLoading && (isConnected ? (
          <div className="github-account">
            <div className="connection-status connected" role="status">
              <span className="status-dot" aria-hidden="true" />
              Connected{connection.githubLogin ? ` as @${connection.githubLogin}` : ''}
            </div>
            <button
              className="github-disconnect-button"
              type="button"
              onClick={handleDisconnect}
              disabled={isLoading}
            >
              Disconnect GitHub
            </button>
          </div>
        ) : (
          <div className="github-connect-section">
            <div className="connection-status disconnected" role="status">
              <span className="status-dot" aria-hidden="true" />
              GitHub not connected
            </div>
            <button
              className="github-connect-button"
              type="button"
              onClick={() => handleConnect(false)}
              disabled={isConnecting}
            >
              {isConnecting ? 'Opening GitHub…' : 'Authorize GitHub'}
            </button>
            <button
              className="sync-secondary-button"
              type="button"
              onClick={() => handleConnect(true)}
              disabled={isConnecting}
            >
              Install GitHub App
            </button>
          </div>
        ))}
      </section>
    </main>
  );
}

export default GitHubConnection;
