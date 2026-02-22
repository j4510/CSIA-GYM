# TROUBLESHOOTING & ERROR FIXES

## Common Errors & Solutions

### 1. Database Error: "unable to open database file"

**Error:**
```
sqlite3.OperationalError: unable to open database file
```

**Solution:**
```bash
# Stop everything
docker compose down

# Remove old volumes
docker volume prune -f

# Rebuild from scratch
docker compose up --build
```

**Cause:** Docker volume permissions issue. Fresh build fixes it.

---

### 2. Port Already in Use

**Error:**
```
Error starting userland proxy: listen tcp4 0.0.0.0:5050: bind: address already in use
```

**Solution:**
```bash
# Check what's using port 5050
lsof -i :5050

# Kill the process or change port in docker-compose.yml:
ports:
  - "8080:5050"  # Use port 8080 instead

docker compose up
```

---

### 3. Template Not Found

**Error:**
```
jinja2.exceptions.TemplateNotFound: challenges/list.html
```

**Solution:**
```bash
# Rebuild to copy new templates
docker compose down
docker compose up --build
```

**Cause:** Template file wasn't copied into container. Build flag forces copy.

---

### 4. Import Error: "No module named 'app'"

**Error:**
```
ModuleNotFoundError: No module named 'app'
```

**Solution:**
```bash
# Check you're in the right directory
cd /path/to/ctf-platform

# Rebuild
docker compose up --build
```

---

### 5. White Background Instead of Black

**Problem:** Some pages show white background instead of black brutalist design.

**Solution:**
The CSS file overrides this automatically, but if you see white:

```bash
# Hard refresh browser
# Chrome/Firefox: Ctrl+Shift+R (Windows) or Cmd+Shift+R (Mac)

# Or clear cache
docker compose restart
```

---

### 6. Admin Panel Not Showing

**Problem:** Logged in but no "ADMIN" button in navbar.

**Solution:**
```bash
# Check if user is admin
docker exec -it ctf-platform python << 'EOF'
from app import create_app, db
from app.models import User

app = create_app()
with app.app_context():
    user = User.query.filter_by(username='your_username').first()
    print(f"Is admin: {user.is_admin}")
    
    # Manually set admin if needed
    user.is_admin = True
    db.session.commit()
    print("✅ Now admin!")
EOF

# Logout and login again
```

---

### 7. Filter Not Working

**Problem:** Category/source filter returns empty results.

**Solution:**
1. Make sure challenges exist first
2. Check spelling: categories are case-sensitive
3. Clear filters and try again

---

### 8. Upvote Not Working

**Problem:** Clicking upvote doesn't increment count.

**Solution:**
```bash
# Check if upvotes column exists
docker exec -it ctf-platform python << 'EOF'
from app import create_app, db
from app.models import CommunityPost

app = create_app()
with app.app_context():
    # Add column if missing
    db.create_all()
    print("✅ Database updated!")
EOF

docker compose restart
```

---

### 9. 403 Forbidden on Admin Routes

**Error:**
```
403 Forbidden
```

**Solution:**
You're not logged in as admin. Either:

1. Login as default admin:
   - Username: `admin`
   - Password: `admin123`

2. Or promote yourself:
```bash
docker exec -it ctf-platform python << 'EOF'
from app import create_app, db
from app.models import User

app = create_app()
with app.app_context():
    user = User.query.filter_by(username='your_username').first()
    user.is_admin = True
    db.session.commit()
EOF
```

---

### 10. Can't Connect to localhost:5050

**Problem:** Browser says "This site can't be reached"

**Checklist:**
```bash
# 1. Is Docker running?
docker ps

# 2. Is container running?
docker ps | grep ctf-platform

# 3. Check logs
docker compose logs

# 4. Restart
docker compose restart

# 5. Check port mapping
docker port ctf-platform
```

---

## Performance Issues

### Slow with 100 Users

**Solutions:**

1. **Check Resources:**
```bash
docker stats ctf-platform
```

2. **Increase Limits in docker-compose.yml:**
```yaml
services:
  web:
    deploy:
      resources:
        limits:
          cpus: '4'  # Increase from 2
          memory: 4G # Increase from 2G
```

3. **Add Index to Database:**
```bash
docker exec -it ctf-platform python << 'EOF'
from app import create_app, db

app = create_app()
with app.app_context():
    db.session.execute("CREATE INDEX IF NOT EXISTS idx_user_email ON users(email)")
    db.session.execute("CREATE INDEX IF NOT EXISTS idx_challenge_category ON challenges(category)")
    db.session.commit()
    print("✅ Indexes created!")
EOF
```

---

## Fresh Start (Nuclear Option)

If everything is broken:

```bash
# Stop and remove everything
docker compose down -v
docker system prune -af
docker volume prune -f

# Delete local database
rm -rf instance/

# Start fresh
docker compose up --build
```

This creates a brand new database with admin account.

---

## Get Help

If issue persists:

1. **Check logs:**
```bash
docker compose logs --tail=100
```

2. **Copy the error message**

3. **Check GitHub issues or contact support**

---

## Prevention Tips

✅ **Always backup before major changes**
✅ **Test on local machine first**
✅ **Use docker compose up --build after code changes**
✅ **Check logs regularly for warnings**
✅ **Keep Docker updated**
