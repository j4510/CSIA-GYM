# FILE ATTACHMENT GUIDE FOR CHALLENGES

## Overview

Challenges can now have file attachments (e.g., encrypted files, binaries, pcap files, images, etc.).

## How File Attachments Work

### 1. Storage Location

Files are stored in: `/app/static/files/`

This directory is:
- Accessible via web (users can download)
- Persistent across container restarts (using Docker volumes)
- Organized by challenge ID

### 2. File Upload Setup

#### Step 1: Create Files Directory

```bash
# Create the directory in your project
mkdir -p app/static/files

# In Docker, it's auto-created
docker compose up
```

#### Step 2: Add Upload Route

The platform already has the `file_attachment` field in the Challenge model. Now add upload functionality:

**Edit `app/routes/admin.py`** - Add file upload when approving challenges:

```python
from werkzeug.utils import secure_filename
import os

ALLOWED_EXTENSIONS = {'zip', 'txt', 'pdf', 'png', 'jpg', 'jpeg', 'pcap', 'bin', 'elf', 'exe'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@admin_bp.route('/challenges/<int:submission_id>/approve', methods=['POST'])
def approve_challenge(submission_id):
    submission = ChallengeSubmission.query.get_or_404(submission_id)
    
    # Handle file upload if present
    file_path = None
    if 'file' in request.files:
        file = request.files['file']
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            # Save with challenge ID prefix
            filename = f"challenge_{submission.id}_{filename}"
            file_path = os.path.join('files', filename)
            file.save(os.path.join('app/static', file_path))
    
    # Create challenge
    challenge = Challenge(
        title=submission.title,
        description=submission.description,
        category=submission.category,
        difficulty=submission.difficulty,
        flag=submission.flag,
        points=submission.points,
        file_attachment=file_path,  # Store path
        author_id=submission.author_id
    )
    
    submission.status = 'approved'
    db.session.add(challenge)
    db.session.commit()
    
    flash(f'Challenge "{challenge.title}" approved!', 'success')
    return redirect(url_for('admin.challenges'))
```

#### Step 3: Update Admin Approval Template

**Edit `app/templates/admin/challenges.html`** - Add file upload input:

```html
<form method="POST" action="{{ url_for('admin.approve_challenge', submission_id=submission.id) }}" 
      enctype="multipart/form-data">
    
    <!-- Existing challenge info -->
    
    <!-- File Upload -->
    <div class="mb-4">
        <label class="block font-bold mb-2">Attach File (Optional):</label>
        <input type="file" name="file" 
               class="w-full p-2 border-2 border-red-600"
               accept=".zip,.txt,.pdf,.png,.jpg,.jpeg,.pcap,.bin,.elf,.exe">
        <p class="text-sm mt-1 opacity-60">
            Supported: ZIP, TXT, PDF, Images, PCAP, Binaries
        </p>
    </div>
    
    <button type="submit" class="bg-green-600 text-black px-4 py-2 font-black">
        ✅ APPROVE & PUBLISH
    </button>
</form>
```

#### Step 4: Display Download Link

**Edit `app/templates/challenges/detail.html`** - Show download button if file exists:

```html
{% if challenge.file_attachment %}
<div class="mb-6 border-4 border-red-600 p-4 bg-black">
    <h3 class="font-black uppercase mb-2">📎 ATTACHMENT</h3>
    <a href="{{ url_for('static', filename=challenge.file_attachment) }}" 
       download
       class="bg-red-600 text-black px-6 py-3 font-black uppercase inline-block hover:bg-white">
        ⬇ DOWNLOAD FILE
    </a>
    <p class="text-sm mt-2 opacity-60">
        File: {{ challenge.file_attachment.split('/')[-1] }}
    </p>
</div>
{% endif %}
```

---

## Quick Implementation Guide

### Method 1: Manual Upload (Easiest)

1. **Upload file via SFTP/SCP to server:**
```bash
scp challenge_file.zip user@server:/path/to/ctf-platform/app/static/files/
```

2. **Update database manually:**
```bash
docker exec -it ctf-platform python << 'EOF'
from app import create_app, db
from app.models import Challenge

app = create_app()
with app.app_context():
    challenge = Challenge.query.get(1)  # Challenge ID
    challenge.file_attachment = 'files/challenge_file.zip'
    db.session.commit()
    print("✅ File attached!")
EOF
```

3. **Verify it works:**
Visit: `http://your-domain.com/static/files/challenge_file.zip`

---

### Method 2: Via Admin Panel (Recommended)

Follow steps 2-4 above to add upload functionality to admin approval page.

---

### Method 3: Direct File Creation

For dynamically generated challenges:

```python
# In your challenge creation script
import os

# Create file
file_path = 'files/dynamic_challenge.txt'
full_path = os.path.join('app/static', file_path)

with open(full_path, 'w') as f:
    f.write("Challenge content here")

# Create challenge with file
challenge = Challenge(
    title="Dynamic Challenge",
    file_attachment=file_path,
    # ... other fields
)
db.session.add(challenge)
db.session.commit()
```

---

## File Types & Security

### Recommended File Types

| Type | Extension | Use Case |
|------|-----------|----------|
| Archives | `.zip`, `.tar.gz` | Multiple files, source code |
| Documents | `.txt`, `.pdf` | Instructions, documents |
| Images | `.png`, `.jpg` | Steganography, visual clues |
| Network | `.pcap`, `.pcapng` | Packet capture analysis |
| Binaries | `.bin`, `.elf`, `.exe` | Reverse engineering |
| Encrypted | `.enc`, `.gpg` | Crypto challenges |

### Security Best Practices

1. **Limit File Size**
```python
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB

@app.before_request
def limit_file_size():
    if request.content_length and request.content_length > MAX_FILE_SIZE:
        abort(413)  # Request Entity Too Large
```

2. **Scan for Malware** (Optional)
```python
import subprocess

def scan_file(filepath):
    # Use ClamAV or similar
    result = subprocess.run(['clamscan', filepath], capture_output=True)
    return result.returncode == 0
```

3. **Use Secure Filenames**
Always use `secure_filename()` from werkzeug (already in example above).

---

## Common Use Cases

### 1. Encrypted ZIP File
```bash
# Create encrypted challenge file
zip -e challenge.zip secret_flag.txt
# Password: ctf2024

# Upload and attach to challenge
```

### 2. Binary Reverse Engineering
```bash
# Compile challenge binary
gcc -o challenge challenge.c

# Strip symbols
strip challenge

# Upload as file attachment
```

### 3. Network Forensics
```bash
# Capture traffic with hidden flag
tcpdump -w challenge.pcap

# Attach to challenge
```

### 4. Steganography
```bash
# Hide data in image
steghide embed -cf image.png -ef secret.txt

# Attach image to challenge
```

---

## Troubleshooting

### File Not Downloading

**Check permissions:**
```bash
docker exec ctf-platform ls -la /app/static/files/
# Should show files with read permissions
```

**Fix permissions:**
```bash
docker exec ctf-platform chmod -R 755 /app/static/files/
```

### File Too Large

**Update nginx config (if using):**
```nginx
client_max_body_size 100M;
```

**Update Docker:**
```yaml
# docker-compose.yml
services:
  web:
    environment:
      - MAX_CONTENT_LENGTH=104857600  # 100MB
```

### File Not Found (404)

**Check path is correct:**
```python
# Should be relative to static/
file_attachment = 'files/challenge.zip'  # ✅ Correct
file_attachment = '/app/static/files/challenge.zip'  # ❌ Wrong
```

---

## Complete Example

### Creating a Challenge with File Attachment

```python
# Create challenge with file
challenge = Challenge(
    title="Crypto Master",
    description="Decrypt the attached file to find the flag.",
    category="crypto",
    difficulty="hard",
    flag="CTF{encrypted_secrets}",
    points=500,
    file_attachment="files/encrypted_challenge.zip",
    author_id=1  # Admin
)

db.session.add(challenge)
db.session.commit()
```

### Template Display

```html
<div class="challenge-detail">
    <h1>{{ challenge.title }}</h1>
    <p>{{ challenge.description }}</p>
    
    {% if challenge.file_attachment %}
    <div class="file-download">
        <a href="{{ url_for('static', filename=challenge.file_attachment) }}" 
           download
           class="download-btn">
            📎 DOWNLOAD CHALLENGE FILE
        </a>
    </div>
    {% endif %}
    
    <!-- Flag submission form -->
</div>
```

---

## Summary

✅ **File Storage:** `/app/static/files/`  
✅ **Access URL:** `http://your-domain/static/files/filename`  
✅ **Database Field:** `challenge.file_attachment`  
✅ **Max Size:** Configure as needed (default 50MB)  
✅ **Security:** Use `secure_filename()` and validate extensions

**Files persist** across container restarts when using Docker volumes!
