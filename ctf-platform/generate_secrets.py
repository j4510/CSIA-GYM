#!/usr/bin/env python3
"""
Run once before first `docker compose up` to populate .env with generated secrets.
Usage: python3 generate_secrets.py
"""
import secrets, os, re

env_path = os.path.join(os.path.dirname(__file__), ".env")
template_path = env_path + ".template"

if not os.path.exists(env_path):
    with open(template_path) as f:
        content = f.read()
    with open(env_path, "w") as f:
        f.write(content)

with open(env_path) as f:
    content = f.read()

def fill(key, value, text):
    pattern = rf"^({re.escape(key)}=)(.*)$"
    if re.search(pattern, text, re.MULTILINE):
        return re.sub(pattern, lambda m: m.group(1) + (m.group(2) or value), text, flags=re.MULTILINE)
    return text + f"\n{key}={value}\n"

if "RUNNER_SECRET=" in content and not re.search(r"^RUNNER_SECRET=.+$", content, re.MULTILINE):
    content = fill("RUNNER_SECRET", secrets.token_hex(32), content)
    print("Generated RUNNER_SECRET")

if "SECRET_KEY=" in content and not re.search(r"^SECRET_KEY=.+$", content, re.MULTILINE):
    content = fill("SECRET_KEY", secrets.token_hex(32), content)
    print("Generated SECRET_KEY")

with open(env_path, "w") as f:
    f.write(content)

print("Done. Edit .env to fill in DATABASE_URL and other settings.")
