# LivingDocs User Registration — LD-35 / LD-36 / LD-37

A starter registration backend using **JavaScript, Node.js, Express, and PostgreSQL**. Includes SQL schema/ERD notes, validation, registration API, and validation unit tests.

> Confirm with your team that this stack matches the repository's backend conventions before merging.

## Requirements

- Node.js 18+
- PostgreSQL
- A terminal and an API client such as Postman or curl

## Setup

1. Create a PostgreSQL database called `livingdocs`.
2. Run `sql/schema.sql` against that database.
3. Copy `.env.example` to `.env`.
4. Update `DATABASE_URL` with your PostgreSQL username/password.
5. Install dependencies and start the API:

```powershell
npm.cmd install
npm.cmd run dev
```

Health check: `GET http://localhost:3000/health`

## Registration endpoint

`POST http://localhost:3000/api/auth/register`

Header: `Content-Type: application/json`

Body:

```json
{
  "username": "minhnguyen",
  "email": "minh@example.com",
  "password": "safe-password-123"
}
```

Expected success: `201 Created`. The API never returns the password or password hash.

Expected errors:
- `400` — missing or invalid input
- `409` — username/email already exists
- `500` — unexpected server error

## Tests

```powershell
npm.cmd test
```

Unit tests cover input validation. API/database integration tests are not included yet.

## Files mapped to tasks

- `sql/schema.sql`: Design User Registration Data (table, primary key, unique fields, role, timestamps, ERD comments).
- `src/validation.js`: Validate Registration Information.
- `src/app.js`, `src/db.js`, `src/server.js`: Develop Registration API.
- `tests/validation.test.js`: Test validation rules.

## Security notes

- Passwords are hashed using bcryptjs before saving.
- SQL uses parameterized queries.
- PostgreSQL unique constraints are authoritative for duplicates.
- The role is assigned by the database default; clients cannot set their own role.
- `.env` is ignored by Git and must not be committed.
- This is registration only, not login, sessions, JWT, OAuth, or email verification.
