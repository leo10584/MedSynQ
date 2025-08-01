const express = require('express');
const session = require('express-session');
const bcrypt = require('bcryptjs');
const path = require('path');

const { db, init, getTenantByName, createTenant } = require('./db');

// Initial setup of database tables.  This ensures that required tables
// exist before handling incoming requests.
init();

const app = express();
const PORT = process.env.PORT || 3000;

// Configure Express to use EJS templating and parse URL‑encoded
// request bodies (submitted by HTML forms).  Static files such as
// CSS, images and favicon are served from the public directory.
app.set('view engine', 'ejs');
app.set('views', path.join(__dirname, 'views'));
app.use(express.urlencoded({ extended: true }));
app.use(
  session({
    secret: 'medsynq_secret_key',
    resave: false,
    saveUninitialized: false,
  })
);
app.use(express.static(path.join(__dirname, 'public')));

// Helper middleware to determine the current tenant based on the
// subdomain or a query parameter.  For simplicity in this demo, a
// `tenant` query parameter can be used (e.g. /login?tenant=myclinic).
// A production environment would inspect req.hostname to derive the
// tenant from the subdomain or custom domain.
app.use((req, res, next) => {
  const tenantQuery = req.query.tenant || (req.session.user && req.session.tenantName);
  if (!tenantQuery) {
    req.tenant = null;
    return next();
  }
  getTenantByName(tenantQuery, (err, tenant) => {
    if (err) {
      return next(err);
    }
    req.tenant = tenant;
    next();
  });
});

// Home page.  If the user is logged in, redirect to dashboard; otherwise
// render a simple landing page describing the application and
// offering links to register a tenant or log in.  The tagline is
// printed here to emphasise the branding.
app.get('/', (req, res) => {
  if (req.session.user) {
    return res.redirect(`/dashboard?tenant=${req.session.tenantName}`);
  }
  res.render('index', {
    error: null,
    user: req.session.user,
    tenantName: req.session.tenantName,
  });
});

// Render the tenant creation form.  This route allows a new
// organisation to sign up to MedSynQ.  The user will provide a
// tenant name, admin username and password.
app.get('/register-tenant', (req, res) => {
  res.render('register-tenant', {
    error: null,
    user: req.session.user,
    tenantName: req.session.tenantName,
  });
});

// Handle tenant registration.  After creating the tenant, an admin
// user is created.  On success, the new admin is logged in and
// redirected to the dashboard.  Errors due to duplicate names are
// surfaced back to the form.
app.post('/register-tenant', (req, res) => {
  const { tenantName, adminName, adminEmail, adminPassword } = req.body;
  if (!tenantName || !adminName || !adminEmail || !adminPassword) {
    return res.render('register-tenant', {
      error: 'All fields are required.',
      user: req.session.user,
      tenantName: req.session.tenantName,
    });
  }
  createTenant(tenantName.trim(), null, (err, tenantId) => {
    if (err) {
      const msg = err.message.includes('UNIQUE') ? 'Tenant name already exists.' : 'Error creating tenant.';
      return res.render('register-tenant', {
        error: msg,
        user: req.session.user,
        tenantName: req.session.tenantName,
      });
    }
    const passwordHash = bcrypt.hashSync(adminPassword, 10);
    db.run(
      'INSERT INTO users (tenant_id, name, email, password_hash) VALUES (?, ?, ?, ?)',
      [tenantId, adminName.trim(), adminEmail.trim(), passwordHash],
      function (userErr) {
        if (userErr) {
          return res.render('register-tenant', {
            error: 'Error creating admin user.',
            user: req.session.user,
            tenantName: req.session.tenantName,
          });
        }
        req.session.user = { id: this.lastID, name: adminName.trim() };
        req.session.tenantId = tenantId;
        req.session.tenantName = tenantName.trim();
        res.redirect(`/dashboard?tenant=${tenantName.trim()}`);
      }
    );
  });
});

// Render login page.  The page allows the user to specify a tenant
// name and their credentials.  If the tenant does not exist, an
// error is displayed.
app.get('/login', (req, res) => {
  res.render('login', {
    error: null,
    user: req.session.user,
    tenantName: req.session.tenantName,
  });
});

// Handle login submissions.  The request must contain tenantName,
// email and password.  The tenant is looked up first; if found the
// user credentials are validated.  On success the session is
// populated with the user and tenant identifiers.
app.post('/login', (req, res) => {
  const { tenantName, email, password } = req.body;
  if (!tenantName || !email || !password) {
    return res.render('login', {
      error: 'All fields are required.',
      user: req.session.user,
      tenantName: req.session.tenantName,
    });
  }
  getTenantByName(tenantName.trim(), (err, tenant) => {
    if (err) {
      return res.render('login', {
        error: 'Error finding tenant.',
        user: req.session.user,
        tenantName: req.session.tenantName,
      });
    }
    if (!tenant) {
      return res.render('login', {
        error: 'Tenant not found.',
        user: req.session.user,
        tenantName: req.session.tenantName,
      });
    }
    db.get(
      'SELECT * FROM users WHERE tenant_id = ? AND email = ?',
      [tenant.id, email.trim()],
      (userErr, user) => {
        if (userErr || !user) {
          return res.render('login', {
            error: 'Invalid email or password.',
            user: req.session.user,
            tenantName: req.session.tenantName,
          });
        }
        if (!bcrypt.compareSync(password, user.password_hash)) {
          return res.render('login', {
            error: 'Invalid email or password.',
            user: req.session.user,
            tenantName: req.session.tenantName,
          });
        }
        req.session.user = { id: user.id, name: user.name };
        req.session.tenantId = tenant.id;
        req.session.tenantName = tenant.name;
        res.redirect(`/dashboard?tenant=${tenant.name}`);
      }
    );
  });
});

// Dashboard displays some tenant‑specific information.  Only logged
// in users can access this route.  A sample list of patients for
// the tenant is displayed.  Patients are scoped by tenant_id to
// enforce isolation.
app.get('/dashboard', (req, res) => {
  if (!req.session.user) {
    return res.redirect('/login');
  }
  const tenantId = req.session.tenantId;
  db.all(
    'SELECT id, name, date_of_birth, notes FROM patients WHERE tenant_id = ?',
    [tenantId],
    (err, patients) => {
      if (err) {
        patients = [];
      }
      res.render('dashboard', {
        user: req.session.user,
        tenantName: req.session.tenantName,
        patients,
      });
    }
  );
});

// Render the form to add a new patient.  Only accessible when logged
// in.  Tenants can add patients who will only be visible to them.
app.get('/patients/new', (req, res) => {
  if (!req.session.user) {
    return res.redirect('/login');
  }
  res.render('new-patient', {
    error: null,
    user: req.session.user,
    tenantName: req.session.tenantName,
  });
});

// Handle new patient submissions.  The patient is saved with the
// current tenant_id to ensure isolation.  After insertion the user
// returns to the dashboard.
app.post('/patients/new', (req, res) => {
  if (!req.session.user) {
    return res.redirect('/login');
  }
  const { name, date_of_birth, notes } = req.body;
  if (!name) {
    return res.render('new-patient', {
      error: 'Name is required.',
      user: req.session.user,
      tenantName: req.session.tenantName,
    });
  }
  const tenantId = req.session.tenantId;
  db.run(
    'INSERT INTO patients (tenant_id, name, date_of_birth, notes) VALUES (?, ?, ?, ?)',
    [tenantId, name.trim(), date_of_birth || null, notes || null],
    function (err) {
      if (err) {
        return res.render('new-patient', {
          error: 'Error saving patient.',
          user: req.session.user,
          tenantName: req.session.tenantName,
        });
      }
      res.redirect(`/dashboard?tenant=${req.session.tenantName}`);
    }
  );
});

// Log out the current user by destroying the session.
app.get('/logout', (req, res) => {
  req.session.destroy(() => {
    res.redirect('/');
  });
});

// Basic error handler to display errors to the user.  In a
// production system you might log the error and render a friendly
// error page instead of returning JSON.
app.use((err, req, res, next) => {
  console.error(err);
  res.status(500).send('Internal Server Error');
});

app.listen(PORT, () => {
  console.log(`MedSynQ server listening on port ${PORT}`);
});