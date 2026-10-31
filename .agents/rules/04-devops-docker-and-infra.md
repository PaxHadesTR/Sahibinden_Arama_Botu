---
description: Docker, CI/CD, cloud automation, and network security rules
trigger: glob
globs: ["**/Dockerfile*", "**/docker-compose*.yml", "**/*.tf", "**/*.sh", "**/*.ps1", "**/*.bat", "**/.github/workflows/*.yml", "**/*.conf"]
---
- **Secret & Artifact Hygiene (V4):** Never commit `.env` files, private keys, live database files (`*.db`, `*.sqlite*`, `*.wal`), or large binary weights to version control. Ensure static file servers block access to sensitive extensions and hidden dotfiles.
- **Proxy & Network Transparency:** When deploying behind reverse proxies or tunnels (Cloudflare Tunnel, Nginx, Traefik, Coolify), properly configure forwarded headers so rate limiters and audit logs capture real client IPs without spoofing vulnerabilities.
- **Idempotent Automation:** Write shell, PowerShell, and deployment scripts to be idempotent, fail-fast on errors, and safe to re-run.
