# MedSynQ – Minimal Multi‑Tenant SaaS Platform

MedSynQ is a proof‑of‑concept multi‑tenant web application built with Python and SQLite.  Each organisation (tenant) has its own users and patient records stored in the same database but isolated via a `tenant_id` column.  The application demonstrates how a single instance of a software service can serve multiple tenants while keeping their data separate.

## Features

* **Tenant registration** – Organisations can sign up via the “Create Organisation” form.  A tenant record is created and an administrator account is provisioned.
* **User authentication** – Users log in by specifying their organisation name, email address and password.  Simple cookie‑based sessions track authenticated users.
* **Tenant isolation** – Patient records are scoped to the tenant that created them.  Users only see patients belonging to their organisation.
* **Patient management** – Tenants can add basic patient data (name, date of birth, notes) and view it in a table.
* **Minimal dependencies** – The application uses only Python’s standard library plus Jinja2 for templating.  No external web frameworks are required.
* **Branding** – Includes a custom logo (see `public/images/logo.png`) and a favicon generated for MedSynQ.  The tagline “Synchronise care across organisations” is visible across all pages.

## Running the application

1. Ensure you have Python 3 installed.  The Jinja2 package should already be available in this environment.  If not, install it via `pip install jinja2`.
2. Initialise the database and start the web server:

   ```bash
   cd medsynq_app
   python server.py
   ```

   The server listens on port `8000` by default.  You can override the port by setting the `PORT` environment variable before running the script.

3. Open your browser and navigate to `http://localhost:8000` to access MedSynQ.  Use the navigation links to create an organisation, log in, add patients and view your dashboard.

## Multi‑tenant architecture overview

MedSynQ follows the **shared database, shared schema** model described in multi‑tenant architecture literature【73636508205984†L85-L113】.  Tenants share the same application code and database, but every table has a `tenant_id` column to isolate data.  This approach is the simplest and most cost‑effective, though it requires careful filtering in queries to prevent data leakage【73636508205984†L85-L113】.  More complex models (such as separate schemas or separate databases per tenant) can offer stronger isolation at the cost of operational complexity【73636508205984†L114-L183】.  MedSynQ’s implementation can be evolved to use those patterns if regulatory requirements demand.

## Logo and favicon

The file `public/images/logo.png` contains a minimal abstract logo for MedSynQ.  A smaller version is provided as `public/favicon.png` for browser tabs.  The tagline is displayed next to the logo throughout the application.

## Security notice

This demonstration stores passwords in plain text and uses an in‑memory session store for simplicity.  A production‑ready system must hash and salt passwords (e.g. using bcrypt), implement secure session management and protect against CSRF and other web‑security threats.  Additionally, the database schema may need to evolve to meet regulatory requirements (e.g. HIPAA) and to support high availability.