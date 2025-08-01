const sqlite3 = require('sqlite3').verbose();
const path = require('path');

// Create or open the SQLite database.  The database file lives in the
// project directory and is created if it doesn't exist.  Using a file
// instead of an in‑memory database allows persistent storage across
// server restarts.
const dbPath = path.join(__dirname, 'database.sqlite');
const db = new sqlite3.Database(dbPath);

// Initialise the database by creating the required tables if they
// haven't been created yet.  This function is idempotent—running it
// multiple times won't overwrite existing tables.  Tenants represent
// customer organisations, while users are associated with a single
// tenant.  A very simple patients table is included to demonstrate
// tenant isolation in queries.
function init() {
  db.serialize(() => {
    db.run(
      `CREATE TABLE IF NOT EXISTS tenants (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        domain TEXT UNIQUE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      )`
    );

    db.run(
      `CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tenant_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        email TEXT NOT NULL,
        password_hash TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (tenant_id) REFERENCES tenants(id)
      )`
    );

    db.run(
      `CREATE TABLE IF NOT EXISTS patients (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tenant_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        date_of_birth TEXT,
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (tenant_id) REFERENCES tenants(id)
      )`
    );
  });
}

// Helper to fetch a tenant by its subdomain or name.  The tenant
// information is used to scope subsequent database operations.  If
// nothing matches the given name, null is returned.
function getTenantByName(name, callback) {
  db.get(
    'SELECT * FROM tenants WHERE name = ? COLLATE NOCASE',
    [name],
    (err, row) => {
      if (err) {
        callback(err);
      } else {
        callback(null, row || null);
      }
    }
  );
}

// Helper to create a new tenant.  Returns the inserted tenant id via
// callback.  Attempting to insert a duplicate tenant name will
// generate a UNIQUE constraint error.  The caller should handle
// errors accordingly.
function createTenant(name, domain, callback) {
  db.run(
    'INSERT INTO tenants (name, domain) VALUES (?, ?)',
    [name, domain],
    function (err) {
      if (err) {
        callback(err);
      } else {
        callback(null, this.lastID);
      }
    }
  );
}

module.exports = {
  db,
  init,
  getTenantByName,
  createTenant,
};