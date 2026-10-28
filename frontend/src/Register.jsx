
import { useState } from 'react';
import { csrfHeaders } from './csrf';

function Register() {
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [message, setMessage] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [hasError, setHasError] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    setMessage('');
    setHasError(false);

    if (password !== confirmPassword) {
      setMessage('Passwords do not match.');
      setHasError(true);
      return;
    }

    setIsSubmitting(true);

    try {
      const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');
      const response = await fetch(`${apiBaseUrl}/api/auth/register`, {
        method: 'POST',
        headers: await csrfHeaders({ 'Content-Type': 'application/json' }, apiBaseUrl),
        credentials: 'include',
        body: JSON.stringify({ username, email, password, firstName, lastName }),
      });

      const result = await response.json().catch(() => ({}));

      if (!response.ok) {
        const validationMessages = result.errors
          ? Object.values(result.errors).flatMap((error) =>
            Array.isArray(error) ? error : [error],
          )
            .map((error) => (typeof error === 'string' ? error : error?.defaultMessage))
            .filter(Boolean)
        : [];
        const errorMessage = result.message
          || result.detail
          || validationMessages.join(' ')
          || (response.status === 409
            ? 'That username or email is already registered.'
            : response.status === 400
              ? 'Please check the registration details and try again.'
              : 'Registration failed. Please try again.');

        throw new Error(errorMessage);
      }

      setMessage(result.message || 'Registration successful.');
    } catch (error) {
      setHasError(true);
      setMessage(error instanceof TypeError
        ? 'Could not connect to the backend. Check that it is running and try again.'
        : error.message || 'Registration failed. Please try again.');
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <main className="page">
      <section className="login-card">
        <h1>Create account</h1>
        <p className="subtitle">Join LivingDocs</p>

        <form onSubmit={handleSubmit}>
          <label htmlFor="register-username">Username</label>
          <input
            id="register-username"
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            minLength={3}
            maxLength={50}
            placeholder="Choose a username"
            required
          />

          <label htmlFor="register-email">Email</label>
          <input
            id="register-email"
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            maxLength={255}
            placeholder="you@example.com"
            required
          />

          <label htmlFor="register-first-name">First name</label>
          <input
            id="register-first-name"
            value={firstName}
            onChange={(event) => setFirstName(event.target.value)}
            maxLength={255}
            required
          />

          <label htmlFor="register-last-name">Last name</label>
          <input
            id="register-last-name"
            value={lastName}
            onChange={(event) => setLastName(event.target.value)}
            maxLength={255}
            required
          />

          <label htmlFor="register-password">Password</label>
          <input
            id="register-password"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            minLength={6}
            maxLength={255}
            placeholder="At least 6 characters"
            required
          />

          <label htmlFor="confirm-password">Confirm password</label>
          <input
            id="confirm-password"
            type="password"
            value={confirmPassword}
            onChange={(event) => setConfirmPassword(event.target.value)}
            placeholder="Enter your password again"
            required
          />

          <button type="submit" disabled={isSubmitting}>
            {isSubmitting ? 'Creating account...' : 'Create account'}
          </button>
        </form>

        {message && <p role={hasError ? 'alert' : 'status'}>{message}</p>}
      </section>
    </main>
  );
}

export default Register;
