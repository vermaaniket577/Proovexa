# ScholarGuard Deployment Guide (Turnitin Clone)

This guide provides complete instructions for deploying the **ScholarGuard Academic Plagiarism & AI Writing Detection Platform** to production environments.

---

## 1. Quick Start: Docker Compose (Recommended)

The easiest way to run the full production stack with MySQL 8.0, Gunicorn, and persistent document volumes is with Docker Compose.

### Step 1: Clone and Configure Environment
```bash
git clone <your-repo-url>
cd plagarismreport
cp .env.example .env
```
Edit `.env` and set a secure `SECRET_KEY`:
```bash
python -c "import secrets; print(secrets.token_urlsafe(50))"
```

### Step 2: Launch the Stack
```bash
docker compose up -d --build
```

### Step 3: Create Admin Account
```bash
docker compose exec web python manage.py createsuperuser
```

### Step 4: Verify Deployment
Visit `http://localhost:8000/` or check health status:
```bash
curl http://localhost:8000/health/
# Returns: {"status": "healthy", "service": "turnitin-plagiarism-core", "database": "ok", "storage": "writable"}
```

---

## 2. Cloud Platform Deployment (Render / Railway / Heroku)

ScholarGuard is pre-configured with `Procfile`, `runtime.txt`, WhiteNoise static file compression, and dynamic `DATABASE_URL` parsing.

### Deploying to Render
1. Create a **New Web Service** connected to your repository.
2. Select **Python** runtime.
3. **Build Command**:
   ```bash
   pip install -r requirements.txt && python manage.py migrate && python manage.py collectstatic --noinput
   ```
4. **Start Command**:
   ```bash
   gunicorn plagiarism_project.wsgi:application --bind 0.0.0.0:$PORT --workers 3
   ```
5. Add **Environment Variables** in the Render Dashboard:
   - `SECRET_KEY`: `<your-random-secret-key>`
   - `DEBUG`: `False`
   - `ALLOWED_HOSTS`: `your-app.onrender.com`
   - `CSRF_TRUSTED_ORIGINS`: `https://your-app.onrender.com`
   - `DATABASE_URL`: Attach a Render PostgreSQL or MySQL database URL.
   - `MAX_UPLOAD_SIZE_MB`: `25`
6. Attach a **Persistent Disk** mounted to `/app/secure_uploads` and `/app/media` to persist uploaded student papers.

---

## 3. Linux VPS Deployment (Ubuntu / Nginx + Gunicorn + Systemd)

### Step 1: Install Dependencies
```bash
sudo apt update && sudo apt install -y python3-pip python3-venv nginx mysql-server
```

### Step 2: Set Up Directory & Virtual Environment
```bash
sudo mkdir -p /var/www/scholarguard
cd /var/www/scholarguard
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### Step 3: Run Database Migrations & Static Files
```bash
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py createsuperuser
```

### Step 4: Configure Systemd Service
Create `/etc/systemd/system/scholarguard.service`:
```ini
[Unit]
Description=ScholarGuard Gunicorn Service
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/var/www/scholarguard
ExecStart=/var/www/scholarguard/venv/bin/gunicorn \
          --config /var/www/scholarguard/gunicorn.conf.py \
          plagiarism_project.wsgi:application
Restart=always

[Install]
WantedBy=multi-user.target
```
Enable and start the service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now scholarguard
```

### Step 5: Configure Nginx Reverse Proxy
Copy the provided [`nginx.conf.example`](file:///d:/plagarismreport/nginx.conf.example) to `/etc/nginx/sites-available/scholarguard`:
```bash
sudo cp nginx.conf.example /etc/nginx/sites-available/scholarguard
sudo ln -s /etc/nginx/sites-available/scholarguard /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

Obtain a free SSL Certificate with Let's Encrypt:
```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
```

---

## 4. Windows Server Deployment (Waitress)

For Windows Server environments, ScholarGuard includes a production runner ([run_production.py](file:///d:/plagarismreport/run_production.py)) powered by Waitress:

```powershell
# In virtual environment:
.\venv\Scripts\python.exe manage.py migrate
.\venv\Scripts\python.exe manage.py collectstatic --noinput
.\venv\Scripts\python.exe run_production.py
```
To run as a Windows Service, use `NSSM` (Non-Sucking Service Manager):
```powershell
nssm install ScholarGuard "d:\plagarismreport\venv\Scripts\python.exe" "d:\plagarismreport\run_production.py"
nssm start ScholarGuard
```

---

## 5. Security & Pre-Flight Verification Checklist

Before launching to live users:

- [x] **DEBUG=False**: Confirmed disabled in production.
- [x] **WhiteNoise**: Static assets bundled, compressed, and served without external web server dependencies.
- [x] **Secure Uploads**: Student files stored in private directory ([secure_uploads/](file:///d:/plagarismreport/secure_uploads)) accessible only via authorized permission checks.
- [x] **Health Check**: Available at `/health/` and `/healthz/` for load balancers.
- [x] **Custom Error Pages**: Styled Turnitin-themed 404, 500, 403, and 400 pages active.
- [x] **Audit Logging**: Every document upload, scan, report view, and delete is recorded in the `AuditLog` database.
