const { Pool } = require('pg');

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  ...(process.env.PGSSL === 'true'
    ? { ssl: { rejectUnauthorized: false } }
    : {})
});

pool.on('error', (error) => {
  console.error('Unexpected PostgreSQL pool error:', error.message);
});

module.exports = {
  query: (sql, params) => pool.query(sql, params),
  pool
};
