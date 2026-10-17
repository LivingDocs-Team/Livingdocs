import { useState } from 'react';

function GitHubConnection() {
  const [isConnected, setIsConnected] = useState(false);

  function handleConnect() {
    // Demo UI only: chưa kết nối OAuth thật.
    setIsConnected(true);
  }

  function handleDisconnect() {
    setIsConnected(false);
  }

  return (
    <main className="page">
      <section className="login-card github-connection-card">
        <h1>GitHub Integration</h1>

        <p className="subtitle">
          Connect your GitHub account to manage repositories in LivingDocs.
        </p>

        <div
          className={`connection-status ${
            isConnected ? 'connected' : 'disconnected'
          }`}
          role="status"
          aria-live="polite"
        >
          <span className="status-dot" aria-hidden="true" />
          {isConnected ? 'GitHub connected' : 'GitHub not connected'}
        </div>

        {isConnected ? (
          <div className="github-account">
            <div className="github-avatar" aria-hidden="true">
              GH
            </div>

            <div className="github-account-info">
              <strong>Demo GitHub Account</strong>
              <span>@demo-user</span>
            </div>

            <p className="github-demo-note">
              This is sample account information for UI testing only.
            </p>

            <button
              className="github-disconnect-button"
              type="button"
              onClick={handleDisconnect}
            >
              Disconnect GitHub
            </button>
          </div>
        ) : (
          <div className="github-connect-section">
            <p>
              Connect your GitHub account to continue to repository
              management.
            </p>

            <button
              className="github-connect-button"
              type="button"
              onClick={handleConnect}
            >
              Connect GitHub
            </button>

            <p className="github-demo-note">
              Demo mode: this button does not connect a real GitHub account.
            </p>
          </div>
        )}

        <p className="github-security-note">
          A real GitHub connection requires OAuth integration with the backend.
        </p>
      </section>
    </main>
  );
}

export default GitHubConnection;