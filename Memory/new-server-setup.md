# New DigitalOcean Server Setup

## 2026-05-14

### Request
User wants to create a second DigitalOcean droplet similar to the current one (Python, SSH, firewall, basics), then build a similar FastAPI web server platform on top of it, with user management for multiple users.

### Step-by-Step Plan Provided

**Phase 1: Create the Droplet**
- Ubuntu 24.04 LTS on DO console, add SSH key at creation time
- Point a domain/subdomain at the droplet IP via DNS A record (needed for SSL)

**Phase 2: Initial Server Hardening**
- `apt update && apt upgrade -y`
- Create non-root user `deploy`, add to sudo group
- Copy SSH key to new user via rsync
- Harden `/etc/ssh/sshd_config`: disable root login, disable password auth
- UFW firewall: allow OpenSSH, 80, 443, then enable

**Phase 3: Install Python & Core Tools**
- `apt install python3 python3-pip python3-venv git nginx certbot python3-certbot-nginx`

**Phase 4: Clone App & Set Up Gunicorn**
- Clone repo as deploy user, create venv, pip install requirements
- Test with `gunicorn -b 127.0.0.1:8000 webapp.app:app`

**Phase 5: Gunicorn as systemd Service**
- Create `/etc/systemd/system/webapp.service` with User=deploy, WorkingDirectory, ExecStart pointing to venv gunicorn
- `systemctl daemon-reload && systemctl enable --now webapp`

**Phase 6: Nginx Reverse Proxy + SSL**
- Create nginx site config proxying to 127.0.0.1:8000 with Host/IP headers
- Symlink to sites-enabled, reload nginx
- Run `certbot --nginx -d yourdomain.com` for Let's Encrypt SSL

**Phase 7: User Management — Two Options**
- **Option A (Simple):** Add users table to SQLite, hash passwords with `passlib`, manage sessions with `itsdangerous` or `starlette-session`. Fits existing single-file pattern. Recommended for personal servers with known users.
- **Option B (Proper):** Use `fastapi-users` library — registration, login, JWT/cookie sessions, password reset. More setup but production-ready. Better if open registration or password reset is needed.

### Open Questions / Next Steps
- User hasn't chosen Option A vs B for user management yet
- Droplet not yet created — user is at planning stage
- Once droplet is up and DNS pointed, adapt app.py for multi-user auth
