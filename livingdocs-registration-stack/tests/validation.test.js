const { validateRegistration } = require('../src/validation');

describe('validateRegistration', () => {
  test('accepts valid information and normalizes email', () => {
    const result = validateRegistration({
      username: '  minhnguyen ',
      email: ' MINH@example.com ',
      password: 'safe-password-123'
    });
    expect(result.errors).toEqual({});
    expect(result.value.username).toBe('minhnguyen');
    expect(result.value.email).toBe('minh@example.com');
  });

  test('requires username, email and password', () => {
    const result = validateRegistration({});
    expect(result.errors.username).toBe('Username is required.');
    expect(result.errors.email).toBe('Email is required.');
    expect(result.errors.password).toBe('Password is required.');
  });

  test('rejects username longer than 50 characters', () => {
    const result = validateRegistration({
      username: 'u'.repeat(51),
      email: 'person@example.com',
      password: 'safe-password-123'
    });
    expect(result.errors.username).toBe('Username must not exceed 50 characters.');
  });

  test('rejects email longer than 255 characters', () => {
    const result = validateRegistration({
      username: 'person',
      email: `${'a'.repeat(244)}@example.com`,
      password: 'safe-password-123'
    });
    expect(result.errors.email).toBe('Email must not exceed 255 characters.');
  });

  test('rejects malformed email', () => {
    const result = validateRegistration({
      username: 'person',
      email: 'not-an-email',
      password: 'safe-password-123'
    });
    expect(result.errors.email).toBe('Please enter a valid email address.');
  });

  test('rejects a password shorter than 8 characters', () => {
    const result = validateRegistration({
      username: 'person',
      email: 'person@example.com',
      password: 'short'
    });
    expect(result.errors.password).toBe('Password must be at least 8 characters.');
  });
});
