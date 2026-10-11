require('dotenv').config();
const express = require('express');
const bcrypt = require('bcryptjs');
const db = require('./db');
const { validateRegistration } = require('./validation');

const app = express();
app.use(express.json({ limit: '20kb' }));

app.get('/health', async (_req, res) => {
  try {
    await db.query('SELECT 1');
    res.status(200).json({ status: 'ok', database: 'connected' });
  } catch (_error) {
    res.status(503).json({ status: 'error', database: 'unavailable' });
  }
});

app.post('/api/auth/register', async (req, res) => {
  const { errors, value } = validateRegistration(req.body);

  if (Object.keys(errors).length) {
    return res.status(400).json({ message: 'Validation failed.', errors });
  }

  try {
    const existing = await db.query(
      `SELECT username, email FROM users
       WHERE LOWER(username) = LOWER($1) OR LOWER(email) = LOWER($2)`,
      [value.username, value.email]
    );

    const duplicateErrors = {};
    if (existing.rows.some((row) => row.username.toLowerCase() === value.username.toLowerCase())) {
      duplicateErrors.username = 'Username is already taken.';
    }
    if (existing.rows.some((row) => row.email.toLowerCase() === value.email.toLowerCase())) {
      duplicateErrors.email = 'Email is already registered.';
    }
    if (Object.keys(duplicateErrors).length) {
      return res.status(409).json({
        message: 'Username or email already exists.',
        errors: duplicateErrors
      });
    }

    const rounds = Number.parseInt(process.env.BCRYPT_ROUNDS || '12', 10);
    const passwordHash = await bcrypt.hash(value.password, rounds);

    const result = await db.query(
      `INSERT INTO users (username, email, password_hash)
       VALUES ($1, $2, $3)
       RETURNING id, username, email, role, created_at, updated_at`,
      [value.username, value.email, passwordHash]
    );

    return res.status(201).json({
      message: 'Registration successful.',
      user: result.rows[0]
    });
  } catch (error) {
    if (error.code === '23505') {
      const field = error.constraint === 'uq_users_username' ? 'username'
        : error.constraint === 'uq_users_email' ? 'email' : null;
      return res.status(409).json({
        message: 'Username or email already exists.',
        ...(field ? {
          errors: {
            [field]: field === 'username'
              ? 'Username is already taken.'
              : 'Email is already registered.'
          }
        } : {})
      });
    }

    console.error('Registration failed:', error.message);
    return res.status(500).json({ message: 'Internal server error.' });
  }
});

app.use((error, _req, res, next) => {
  if (error instanceof SyntaxError && error.status === 400 && 'body' in error) {
    return res.status(400).json({ message: 'Request body must be valid JSON.' });
  }
  return next(error);
});

module.exports = app;
