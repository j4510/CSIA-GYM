# CTF Platform

A modular Capture The Flag (CTF) platform built with Flask. Features include user authentication, challenge management, community discussions, and user-submitted challenges.

## Features

- ✅ **User Authentication** - Register, login, and manage profiles
- 🎯 **Challenges** - Browse, solve, and submit flags
- 🏆 **Scoreboard** - Real-time leaderboard
- 📝 **Submit Challenges** - Users can submit their own challenges for approval
- 💬 **Community** - Discussion board for writeups and questions
- ⚙️ **Settings** - User profile management

## Project Structure

```
ctf-platform/
├── app/
│   ├── __init__.py          # App factory and configuration
│   ├── models.py            # Database models
│   ├── routes/              # Route blueprints (modular)
│   │   ├── auth.py          # Authentication routes
│   │   ├── challenges.py    # Challenge routes
│   │   ├── submissions.py   # User submission routes
│   │   ├── community.py     # Community/forum routes
│   │   └── settings.py      # Settings routes
│   ├── templates/           # HTML templates
│   │   ├── base.html        # Base template (navigation)
│   │   ├── index.html       # Homepage
│   │   ├── auth/            # Auth templates
│   │   ├── challenges/      # Challenge templates
│   │   ├── submissions/     # Submission templates
│   │   ├── community/       # Community templates
│   │   └── settings.html    # Settings template
│   └── static/              # CSS, JS, images (add as needed)
├── config.py                # Configuration settings
├── run.py                   # Application entry point
├── requirements.txt         # Python dependencies
├── Dockerfile               # Docker image definition
├── docker-compose.yml       # Docker Compose configuration
└── README.md               # This file
```

## Quick Start

### Option 1: Run with Docker (Recommended)

1. **Install Docker Desktop**
   - Download from: https://www.docker.com/products/docker-desktop/

2. **Clone or download this project**
   ```bash
   cd ctf-platform
   ```

3. **Start the application**
   ```bash
   docker compose up
   ```

4. **Access the platform**
   - Open browser: http://localhost:5050
   - Register an account and start using!

5. **Stop the application**
   ```bash
   docker compose down
   ```

### Option 2: Run Locally (Without Docker)

1. **Install Python 3.11+**
   - Download from: https://www.python.org/downloads/

2. **Create virtual environment**
   ```bash
   python -m venv venv
   
   # On Mac/Linux:
   source venv/bin/activate
   
   # On Windows:
   venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Run the application**
   ```bash
   python run.py
   ```

5. **Access the platform**
   - Open browser: http://localhost:5050

## Deployment to Production Server

### Step 1: Get a Server

Rent a VPS from:
- DigitalOcean (https://digitalocean.com) - $12/month
- Hetzner (https://hetzner.com) - ~$5/month
- AWS, Google Cloud, or your university's servers

Recommended specs for 100 users:
- 2 vCPU
- 2-4 GB RAM
- 20 GB storage
- Ubuntu 22.04 LTS

### Step 2: Set Up Server

SSH into your server:
```bash
ssh root@your-server-ip
```

Install Docker:
```bash
# Update system
apt update && apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh

# Install Docker Compose
apt install docker-compose-plugin -y
```

### Step 3: Deploy Application

1. **Clone your code to server**
   ```bash
   git clone https://github.com/yourteam/ctf-platform.git
   cd ctf-platform
   ```

2. **Configure environment**
   Edit `docker-compose.yml` and change:
   - `SECRET_KEY` to a random string
   - Set `FLASK_ENV=production`

3. **Start the application**
   ```bash
   docker compose up -d
   ```

### Step 4: Set Up Domain and SSL

1. **Point domain to server**
   - In your DNS settings, add an A record:
   - Name: `ctf` (or `@` for root domain)
   - Value: Your server IP
   - Example: `ctf.yourdept.edu` → `167.99.45.12`

2. **Install Nginx**
   ```bash
   apt install nginx -y
   ```

3. **Configure Nginx**
   Create `/etc/nginx/sites-available/ctf`:
   ```nginx
   server {
       listen 80;
       server_name ctf.yourdept.edu;

       location / {
           proxy_pass http://localhost:5000;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
       }
   }
   ```

   Enable the site:
   ```bash
   ln -s /etc/nginx/sites-available/ctf /etc/nginx/sites-enabled/
   nginx -t
   systemctl restart nginx
   ```

4. **Get SSL Certificate**
   ```bash
   apt install certbot python3-certbot-nginx -y
   certbot --nginx -d ctf.yourdept.edu
   ```

Your site is now live at `https://ctf.yourdept.edu`!

## Adding New Features

The platform is designed to be modular. Here's how to add new sections:

### 1. Create a New Blueprint

Create `app/routes/your_feature.py`:
```python
from flask import Blueprint, render_template
from flask_login import login_required

your_feature_bp = Blueprint('your_feature', __name__)

@your_feature_bp.route('/your-route')
@login_required
def index():
    return render_template('your_feature/index.html')
```

### 2. Register the Blueprint

In `app/__init__.py`, add:
```python
from app.routes.your_feature import your_feature_bp
app.register_blueprint(your_feature_bp)
```

### 3. Add to Navigation

In `app/templates/base.html`, add:
```html
<a href="{{ url_for('your_feature.index') }}" 
   class="hover:text-blue-200 transition font-medium">
    Your Feature
</a>
```

### 4. Create Templates

Create `app/templates/your_feature/index.html`:
```html
{% extends "base.html" %}

{% block content %}
<h1>Your Feature</h1>
{% endblock %}
```

## Customization Guide

### Change Color Scheme

Edit `app/templates/base.html` and modify Tailwind classes:
- Navigation: Change `bg-blue-600` to other colors
- Buttons: Change `bg-blue-600` throughout templates

### Add Database Fields

1. Edit `app/models.py` to add fields
2. Restart the app (tables auto-create)
3. For production: Use Flask-Migrate for migrations

### Enable File Uploads

1. Install Pillow: Add to `requirements.txt`
2. Uncomment file upload code in models/routes
3. Create uploads directory

## Common Tasks

### Create Admin User

Add to `app/__init__.py` in create_app():
```python
with app.app_context():
    db.create_all()
    if not User.query.filter_by(username='admin').first():
        admin = User(username='admin', email='admin@example.com')
        admin.set_password('changeme')
        db.session.add(admin)
        db.session.commit()
```

### Backup Database

```bash
# If using SQLite:
docker cp ctf-platform:/app/instance/ctf.db ./backup.db

# If using PostgreSQL:
docker exec ctf-postgres pg_dump -U ctfuser ctfdb > backup.sql
```

### View Logs

```bash
docker compose logs -f
```

### Restart Application

```bash
docker compose restart
```

## Troubleshooting

**Problem: Can't access localhost:5000**
- Check if container is running: `docker ps`
- Check logs: `docker compose logs`

**Problem: Database not persisting**
- Make sure `instance/` directory exists
- Check volume mounts in docker-compose.yml

**Problem: Changes not showing**
- Rebuild: `docker compose up --build`
- Clear browser cache

**Problem: Port 5000 already in use**
- Change port in docker-compose.yml: `"8000:5000"`

## Security Notes

For production deployment:
- [ ] Change SECRET_KEY to a random value
- [ ] Set FLASK_ENV=production
- [ ] Use PostgreSQL instead of SQLite
- [ ] Enable HTTPS with SSL certificate
- [ ] Set up firewall (UFW)
- [ ] Regular backups
- [ ] Keep dependencies updated

## Support

For issues or questions:
1. Check this README
2. Review code comments (extensive documentation in files)
3. Check Flask documentation: https://flask.palletsprojects.com/

## License

Built for your department. Customize as needed!
