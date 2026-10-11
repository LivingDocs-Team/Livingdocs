function validateRegistration(input = {}) {
  const errors = {};

  const username = typeof input.username === 'string' ? input.username.trim() : '';
  const email = typeof input.email === 'string' ? input.email.trim().toLowerCase() : '';
  const password = typeof input.password === 'string' ? input.password : '';

  if (!username) {
    errors.username = 'Username is required.';
  } else if (username.length > 50) {
    errors.username = 'Username must not exceed 50 characters.';
  }

  if (!email) {
    errors.email = 'Email is required.';
  } else if (email.length > 255) {
    errors.email = 'Email must not exceed 255 characters.';
  } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    errors.email = 'Please enter a valid email address.';
  }

  if (!password) {
    errors.password = 'Password is required.';
  } else if (password.length < 8) {
    errors.password = 'Password must be at least 8 characters.';
  } else if (Buffer.byteLength(password, 'utf8') > 72) {
    errors.password = 'Password must not exceed 72 bytes.';
  }

  return { errors, value: { username, email, password } };
}

module.exports = { validateRegistration };
