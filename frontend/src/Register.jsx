
import { useState } from 'react';
import AuthField from './AuthField';
import { csrfHeaders } from './csrf';
import Icon from './icons';

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
              : `Registration failed (HTTP ${response.status}). Please try again.`);

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
    <section aria-labelledby="register-title">
      <div className="auth-icon"><Icon name="user" size={17} /></div>
      <h2 id="register-title">Create your account</h2>
      <p className="auth-sub">Registration creates a Developer account. Other roles are assigned by an Administrator.</p>

      <form onSubmit={handleSubmit}>
        <div className="auth-pair">
          <AuthField
            id="register-first-name"
            label="First name"
            value={firstName}
            onChange={(event) => setFirstName(event.target.value)}
            maxLength={255}
            placeholder="First name"
            required
          />
          <AuthField
            id="register-last-name"
            label="Last name"
            value={lastName}
            onChange={(event) => setLastName(event.target.value)}
            maxLength={255}
            placeholder="Last name"
            required
          />
        </div>

        <AuthField
          id="register-username"
          label="Username"
          icon="user"
          value={username}
          onChange={(event) => setUsername(event.target.value)}
          minLength={3}
          maxLength={50}
          placeholder="Choose a username"
          required
        />

        <AuthField
          id="register-email"
          label="Email"
          icon="mail"
          type="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          maxLength={255}
          placeholder="you@example.com"
          required
        />

        <div className="auth-pair">
          <AuthField
            id="register-password"
            label="Password"
            icon="lock"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            minLength={6}
            maxLength={255}
            placeholder="At least 6 characters"
            required
          />
          <AuthField
            id="confirm-password"
            label="Confirm password"
            icon="lock"
            type="password"
            value={confirmPassword}
            onChange={(event) => setConfirmPassword(event.target.value)}
            placeholder="Enter your password again"
            required
          />
        </div>

        <button className="auth-submit" type="submit" disabled={isSubmitting}>
          {isSubmitting ? 'Creating account...' : 'Create account'}
          <Icon name="arrow" />
        </button>
      </form>

      {message && <p className="auth-message" role={hasError ? 'alert' : 'status'}>{message}</p>}
    </section>
  );
}

export default Register;
