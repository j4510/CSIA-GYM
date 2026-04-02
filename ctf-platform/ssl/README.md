# SSL Certificates

This directory is excluded from version control (see `.gitignore`).

Place your TLS certificate and private key here before running in production:

```
ssl/
├── haucsia.com.pem   # full-chain certificate (PEM)
└── haucsia.com.key   # private key (PEM) — keep secret, never commit
```

## Obtaining certificates

Use [Certbot](https://certbot.eff.org/) with Let's Encrypt:

```bash
certbot certonly --standalone -d haucsia.com
cp /etc/letsencrypt/live/haucsia.com/fullchain.pem ssl/haucsia.com.pem
cp /etc/letsencrypt/live/haucsia.com/privkey.pem   ssl/haucsia.com.key
chmod 600 ssl/haucsia.com.key
```

The `docker-compose.prod.yml` mounts this directory into the nginx container at `/etc/nginx/ssl` read-only.
**Never commit the `.key` or `.pem` files to source control.**
