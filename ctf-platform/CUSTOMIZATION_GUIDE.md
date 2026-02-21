# Customization Guide

This guide explains how to extend and customize the CTF platform.

## Table of Contents

1. [Adding New Sections to Navbar](#adding-new-sections)
2. [Modifying Design/Styling](#design-customization)
3. [Adding Database Models](#database-models)
4. [Common Feature Examples](#feature-examples)

---

## Adding New Sections

### Complete Example: Adding a "Resources" Section

**Step 1: Create the Model (if needed)**

Edit `app/models.py`:
```python
class Resource(db.Model):
    __tablename__ = 'resources'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    url = db.Column(db.String(500), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
```

**Step 2: Create the Blueprint**

Create `app/routes/resources.py`:
```python
from flask import Blueprint, render_template
from flask_login import login_required
from app.models import Resource

resources_bp = Blueprint('resources', __name__)

@resources_bp.route('/resources')
@login_required
def list():
    resources = Resource.query.all()
    return render_template('resources/list.html', resources=resources)
```

**Step 3: Register Blueprint**

In `app/__init__.py`, add these lines:
```python
# In imports section
from app.routes.resources import resources_bp

# In register blueprints section
app.register_blueprint(resources_bp)
```

**Step 4: Create Template**

Create `app/templates/resources/list.html`:
```html
{% extends "base.html" %}

{% block title %}Resources - CTF Platform{% endblock %}

{% block content %}
<h1 class="text-3xl font-bold mb-6">Learning Resources</h1>

<div class="grid md:grid-cols-2 gap-6">
    {% for resource in resources %}
    <div class="bg-white p-6 rounded-lg shadow-md">
        <h3 class="text-xl font-bold mb-2">{{ resource.title }}</h3>
        <span class="text-sm text-gray-500">{{ resource.category }}</span>
        <a href="{{ resource.url }}" target="_blank" 
           class="block mt-4 text-blue-600 hover:underline">
            Visit Resource →
        </a>
    </div>
    {% endfor %}
</div>
{% endblock %}
```

**Step 5: Add to Navigation**

In `app/templates/base.html`, find the navigation section and add:
```html
<a href="{{ url_for('resources.list') }}" 
   class="hover:text-blue-200 transition font-medium">
    Resources
</a>
```

Done! Restart the app and you'll see "Resources" in the navbar.

---

## Design Customization

### Changing Color Scheme

**Primary Color (Blue → Purple):**

In `app/templates/base.html`:
```html
<!-- Change navigation bar -->
<nav class="bg-gradient-to-r from-purple-600 to-purple-700 text-white shadow-lg">

<!-- Change buttons throughout -->
<!-- From: -->
<button class="bg-blue-600 hover:bg-blue-700">
<!-- To: -->
<button class="bg-purple-600 hover:bg-purple-700">
```

Do the same replacement in all template files.

### Adding Custom CSS

1. Create `app/static/css/custom.css`:
```css
/* Custom styles */
.challenge-card {
    border-left: 4px solid #3B82F6;
}

.challenge-card:hover {
    transform: translateY(-2px);
    transition: transform 0.2s;
}
```

2. In `app/templates/base.html`, uncomment:
```html
<link rel="stylesheet" href="{{ url_for('static', filename='css/custom.css') }}">
```

3. Use your custom classes in templates:
```html
<div class="challenge-card bg-white p-6">
    ...
</div>
```

### Adding Custom JavaScript

1. Create `app/static/js/main.js`:
```javascript
// Auto-hide flash messages after 5 seconds
document.addEventListener('DOMContentLoaded', function() {
    setTimeout(function() {
        const alerts = document.querySelectorAll('[class*="bg-green"], [class*="bg-red"]');
        alerts.forEach(alert => {
            alert.style.display = 'none';
        });
    }, 5000);
});
```

2. In `app/templates/base.html`, uncomment:
```html
<script src="{{ url_for('static', filename='js/main.js') }}"></script>
```

---

## Database Models

### Adding Fields to Existing Models

**Example: Add bio to User model**

In `app/models.py`:
```python
class User(UserMixin, db.Model):
    # ... existing fields ...
    bio = db.Column(db.Text, nullable=True)  # Add this line
```

Update templates and forms to use the new field.

### Creating Relationships

**Example: Add tags to challenges**

```python
# Many-to-many relationship
challenge_tags = db.Table('challenge_tags',
    db.Column('challenge_id', db.Integer, db.ForeignKey('challenges.id')),
    db.Column('tag_id', db.Integer, db.ForeignKey('tags.id'))
)

class Tag(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True)
    challenges = db.relationship('Challenge', secondary=challenge_tags, backref='tags')

# Add to Challenge model:
# tags = db.relationship('Tag', secondary=challenge_tags, backref='challenges')
```

---

## Feature Examples

### Example 1: Add Profile Pictures

**1. Install Pillow**
Add to `requirements.txt`:
```
Pillow==10.1.0
```

**2. Update User Model**
```python
class User(UserMixin, db.Model):
    # ... existing fields ...
    profile_picture = db.Column(db.String(200), default='default.png')
```

**3. Add Upload Route**
In `app/routes/settings.py`:
```python
import os
from werkzeug.utils import secure_filename

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@settings_bp.route('/upload-avatar', methods=['POST'])
@login_required
def upload_avatar():
    if 'avatar' not in request.files:
        flash('No file uploaded', 'danger')
        return redirect(url_for('settings.index'))
    
    file = request.files['avatar']
    if file and allowed_file(file.filename):
        filename = secure_filename(f"{current_user.id}_{file.filename}")
        filepath = os.path.join('app/static/avatars', filename)
        file.save(filepath)
        
        current_user.profile_picture = filename
        db.session.commit()
        flash('Profile picture updated!', 'success')
    
    return redirect(url_for('settings.index'))
```

**4. Update Template**
In `app/templates/settings.html`:
```html
<form method="POST" action="{{ url_for('settings.upload_avatar') }}" enctype="multipart/form-data">
    <input type="file" name="avatar" accept="image/*">
    <button type="submit">Upload</button>
</form>
```

### Example 2: Add Markdown Support

**1. Install markdown2**
Add to `requirements.txt`:
```
markdown2==2.4.10
bleach==6.1.0
```

**2. Create Helper Function**
Create `app/utils.py`:
```python
import markdown2
import bleach

def render_markdown(text):
    # Convert markdown to HTML
    html = markdown2.markdown(text, extras=['fenced-code-blocks'])
    # Sanitize HTML to prevent XSS
    clean_html = bleach.clean(html, tags=['p', 'br', 'strong', 'em', 'code', 'pre', 'h1', 'h2', 'h3', 'ul', 'ol', 'li'])
    return clean_html
```

**3. Use in Template**
In `app/templates/community/view.html`:
```html
{% from 'macros.html' import render_markdown %}

<div class="prose">
    {{ post.content|markdown|safe }}
</div>
```

**4. Create Jinja Filter**
In `app/__init__.py`:
```python
from app.utils import render_markdown

def create_app():
    # ... existing code ...
    
    @app.template_filter('markdown')
    def markdown_filter(text):
        return render_markdown(text)
    
    return app
```

### Example 3: Add Search Functionality

**1. Add Search Route**
In `app/routes/challenges.py`:
```python
@challenges_bp.route('/challenges/search')
@login_required
def search():
    query = request.args.get('q', '')
    if query:
        challenges = Challenge.query.filter(
            (Challenge.title.contains(query)) | 
            (Challenge.description.contains(query))
        ).all()
    else:
        challenges = []
    
    return render_template('challenges/search.html', 
                         challenges=challenges, 
                         query=query)
```

**2. Add Search Form**
In `app/templates/challenges/list.html`:
```html
<form action="{{ url_for('challenges.search') }}" method="GET" class="mb-6">
    <div class="flex">
        <input type="text" 
               name="q" 
               placeholder="Search challenges..." 
               class="flex-1 px-4 py-2 border rounded-l-lg">
        <button type="submit" 
                class="bg-blue-600 text-white px-6 py-2 rounded-r-lg">
            Search
        </button>
    </div>
</form>
```

### Example 4: Add Admin Panel

**1. Add is_admin Field**
In `app/models.py`:
```python
class User(UserMixin, db.Model):
    # ... existing fields ...
    is_admin = db.Column(db.Boolean, default=False)
```

**2. Create Admin Decorator**
Create `app/decorators.py`:
```python
from functools import wraps
from flask import flash, redirect, url_for
from flask_login import current_user

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('Admin access required', 'danger')
            return redirect(url_for('auth.index'))
        return f(*args, **kwargs)
    return decorated_function
```

**3. Create Admin Routes**
Create `app/routes/admin.py`:
```python
from flask import Blueprint, render_template
from flask_login import login_required
from app.decorators import admin_required
from app.models import User, Challenge, ChallengeSubmission

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

@admin_bp.route('/')
@login_required
@admin_required
def dashboard():
    stats = {
        'users': User.query.count(),
        'challenges': Challenge.query.count(),
        'pending_submissions': ChallengeSubmission.query.filter_by(status='pending').count()
    }
    return render_template('admin/dashboard.html', stats=stats)
```

**4. Add to Navigation (Admin Only)**
In `app/templates/base.html`:
```html
{% if current_user.is_admin %}
<a href="{{ url_for('admin.dashboard') }}" 
   class="hover:text-blue-200 transition font-medium">
    Admin Panel
</a>
{% endif %}
```

---

## Tips for Clean Code

1. **Keep routes short** - Move complex logic to separate functions
2. **Use comments** - Explain why, not what
3. **Test changes** - Run the app after each modification
4. **Commit often** - Use git to track changes
5. **Follow patterns** - Look at existing code for examples

## Getting Help

- Check existing code for examples
- Read Flask docs: https://flask.palletsprojects.com/
- Read Tailwind docs: https://tailwindcss.com/
- Search for Flask tutorials for specific features

---

Happy customizing! 🚀
