import http.server
import socketserver
import sqlite3
import os
import urllib.parse
import uuid
from http import cookies
from jinja2 import Environment, FileSystemLoader


# -----------------------------------------------------------------------------
# MedSynQ minimal multi‑tenant SaaS platform
#
# This Python script implements a simple HTTP server using only Python's
# standard library and Jinja2 for template rendering.  It provides user
# authentication, tenant registration and isolation of patient records.  Each
# tenant has its own set of users and patients stored in a SQLite database.  A
# cookie‑based session mechanism associates logged‑in users with their tenant
# context.  This implementation is intentionally simple to run in restricted
# environments where third‑party web frameworks cannot be installed.
# -----------------------------------------------------------------------------


DB_PATH = os.path.join(os.path.dirname(__file__), 'database.sqlite')
TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), 'templates')
PUBLIC_DIR = os.path.join(os.path.dirname(__file__), 'public')

env = Environment(loader=FileSystemLoader(TEMPLATES_DIR))

# In‑memory session store.  Keys are session IDs, values are dictionaries
# containing user_id and tenant_id.
SESSIONS = {}


def init_db():
    """Initialise database tables if they do not already exist."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Tenants table
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS tenants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    # Users table
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            password TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (tenant_id) REFERENCES tenants(id)
        )
        """
    )
    # Patients table
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS patients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            date_of_birth TEXT,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (tenant_id) REFERENCES tenants(id)
        )
        """
    )
    conn.commit()
    conn.close()


def render_template(template_name, **context):
    template = env.get_template(template_name)
    return template.render(**context)


class MedSynQHandler(http.server.SimpleHTTPRequestHandler):
    """
    HTTP request handler for MedSynQ.  Supports GET and POST endpoints
    for tenant registration, user authentication, patient management and
    static file serving.
    """

    def do_GET(self):
        parsed_path = urllib.parse.urlparse(self.path)
        path = parsed_path.path

        # Serve static files from /public
        if path.startswith('/public/'):
            return self.serve_static(path)

        # Determine current user session, if any
        session = self.get_session()

        if path == '/':
            self.respond(render_template('index.html', user=session, error=None))
        elif path == '/register-tenant':
            self.respond(render_template('register_tenant.html', user=session, error=None))
        elif path == '/login':
            self.respond(render_template('login.html', user=session, error=None))
        elif path == '/dashboard':
            if not session:
                return self.redirect('/login')
            return self.render_dashboard(session)
        elif path == '/patients/new':
            if not session:
                return self.redirect('/login')
            self.respond(render_template('new_patient.html', user=session, error=None))
        elif path == '/logout':
            return self.handle_logout()
        else:
            self.send_error(404, 'Not Found')

    def do_POST(self):
        parsed_path = urllib.parse.urlparse(self.path)
        path = parsed_path.path

        if path == '/register-tenant':
            return self.handle_register_tenant()
        elif path == '/login':
            return self.handle_login()
        elif path == '/patients/new':
            return self.handle_new_patient()
        else:
            self.send_error(404, 'Not Found')

    # ------------------------------------------------------------------
    # Helper methods

    def serve_static(self, path):
        file_path = os.path.join(os.path.dirname(__file__), path.lstrip('/'))
        if not os.path.isfile(file_path):
            return self.send_error(404, 'File Not Found')
        self.send_response(200)
        self.send_header('Content-Type', self.guess_type(file_path))
        self.end_headers()
        with open(file_path, 'rb') as f:
            self.wfile.write(f.read())

    def parse_post_data(self):
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length).decode('utf-8')
        return urllib.parse.parse_qs(body)

    def get_session(self):
        """
        Retrieve the current session details based on the session_id cookie.
        Returns a dictionary with keys id, user_name, tenant_name if logged in,
        otherwise None.
        """
        if 'Cookie' not in self.headers:
            return None
        cookie_header = self.headers['Cookie']
        try:
            cookie = cookies.SimpleCookie()
            cookie.load(cookie_header)
            if 'session_id' in cookie:
                session_id = cookie['session_id'].value
                session_data = SESSIONS.get(session_id)
                if session_data:
                    return session_data
        except Exception:
            return None
        return None

    def set_session(self, user_id, user_name, tenant_id, tenant_name):
        session_id = str(uuid.uuid4())
        SESSIONS[session_id] = {
            'id': user_id,
            'user_name': user_name,
            'tenant_id': tenant_id,
            'tenant_name': tenant_name,
        }
        # Set cookie
        cookie = cookies.SimpleCookie()
        cookie['session_id'] = session_id
        cookie['session_id']['path'] = '/'
        # Secure and HttpOnly flags could be set in a production environment
        self.send_response(302)
        self.send_header('Set-Cookie', cookie.output(header='', sep=''))
        return session_id

    def clear_session(self):
        cookie = cookies.SimpleCookie()
        cookie['session_id'] = ''
        cookie['session_id']['path'] = '/'
        cookie['session_id']['expires'] = 'Thu, 01 Jan 1970 00:00:00 GMT'
        self.send_response(302)
        self.send_header('Set-Cookie', cookie.output(header='', sep=''))
        return

    def redirect(self, location):
        self.send_response(302)
        self.send_header('Location', location)
        self.end_headers()

    def respond(self, html):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        if isinstance(html, str):
            html = html.encode('utf-8')
        self.wfile.write(html)

    # ------------------------------------------------------------------
    # Route handlers

    def handle_register_tenant(self):
        data = self.parse_post_data()
        tenant_name = data.get('tenantName', [''])[0].strip()
        admin_name = data.get('adminName', [''])[0].strip()
        admin_email = data.get('adminEmail', [''])[0].strip()
        admin_password = data.get('adminPassword', [''])[0]
        if not tenant_name or not admin_name or not admin_email or not admin_password:
            html = render_template('register_tenant.html', user=None, error='All fields are required.')
            return self.respond(html)
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        try:
            c.execute('INSERT INTO tenants (name) VALUES (?)', (tenant_name,))
            tenant_id = c.lastrowid
            c.execute(
                'INSERT INTO users (tenant_id, name, email, password) VALUES (?, ?, ?, ?)',
                (tenant_id, admin_name, admin_email, admin_password),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            conn.close()
            html = render_template('register_tenant.html', user=None, error='Organisation name already exists.')
            return self.respond(html)
        conn.close()
        # Log the new admin in
        session_id = self.set_session(
            user_id=c.lastrowid,
            user_name=admin_name,
            tenant_id=tenant_id,
            tenant_name=tenant_name,
        )
        # Redirect to dashboard
        self.send_header('Location', '/dashboard')
        self.end_headers()

    def handle_login(self):
        data = self.parse_post_data()
        tenant_name = data.get('tenantName', [''])[0].strip()
        email = data.get('email', [''])[0].strip()
        password = data.get('password', [''])[0]
        if not tenant_name or not email or not password:
            html = render_template('login.html', user=None, error='All fields are required.')
            return self.respond(html)
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('SELECT id FROM tenants WHERE name = ?', (tenant_name,))
        tenant_row = c.fetchone()
        if not tenant_row:
            conn.close()
            html = render_template('login.html', user=None, error='Organisation not found.')
            return self.respond(html)
        tenant_id = tenant_row[0]
        c.execute(
            'SELECT id, name, password FROM users WHERE tenant_id = ? AND email = ?',
            (tenant_id, email),
        )
        user_row = c.fetchone()
        conn.close()
        if not user_row or user_row[2] != password:
            html = render_template('login.html', user=None, error='Invalid credentials.')
            return self.respond(html)
        user_id, user_name, _ = user_row
        # Set session and redirect
        self.set_session(user_id, user_name, tenant_id, tenant_name)
        self.send_header('Location', '/dashboard')
        self.end_headers()

    def handle_new_patient(self):
        session = self.get_session()
        if not session:
            return self.redirect('/login')
        data = self.parse_post_data()
        name = data.get('name', [''])[0].strip()
        dob = data.get('date_of_birth', [''])[0]
        notes = data.get('notes', [''])[0]
        if not name:
            html = render_template('new_patient.html', user=session, error='Name is required.')
            return self.respond(html)
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            'INSERT INTO patients (tenant_id, name, date_of_birth, notes) VALUES (?, ?, ?, ?)',
            (session['tenant_id'], name, dob if dob else None, notes if notes else None),
        )
        conn.commit()
        conn.close()
        return self.redirect('/dashboard')

    def handle_logout(self):
        self.clear_session()
        # Remove session from in‑memory store
        session = self.get_session()
        if session:
            for sid, data in list(SESSIONS.items()):
                if data['id'] == session['id']:
                    del SESSIONS[sid]
                    break
        self.send_header('Location', '/')
        self.end_headers()

    def render_dashboard(self, session):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            'SELECT name, date_of_birth, notes FROM patients WHERE tenant_id = ?',
            (session['tenant_id'],),
        )
        patients = [
            {
                'name': row[0],
                'date_of_birth': row[1] or '',
                'notes': row[2] or '',
            }
            for row in c.fetchall()
        ]
        conn.close()
        html = render_template(
            'dashboard.html',
            user=session,
            patients=patients,
        )
        self.respond(html)


# Create database and start the server if run directly
if __name__ == '__main__':
    init_db()
    # Create the templates directory structure if needed
    os.makedirs(TEMPLATES_DIR, exist_ok=True)
    os.makedirs(PUBLIC_DIR, exist_ok=True)
    PORT = int(os.environ.get('PORT', 8000))
    with socketserver.TCPServer(("", PORT), MedSynQHandler) as httpd:
        print(f"MedSynQ Python server running on http://localhost:{PORT}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nServer stopped")