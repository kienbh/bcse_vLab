# Deployment scripts

These are paramiko/urllib helpers for deploying VJU Lab Portal to BCSE VPS pool.
Pattern follows the existing `Server Management/deploy_*.py` scripts.

## Prereqs (on dev machine)

```bash
pip install paramiko
```

Environment variables (defaults match the BCSE infra):

```
BCSE_JUMP_HOST=123.16.53.250
BCSE_JUMP_PORT=2223
BCSE_JUMP_USER=root
SV14_IP=192.168.2.114
SV08_IP=192.168.2.108
VPS_USER=root
CF_API_TOKEN=...           # for cf_dns_sv14.py (default value baked-in)
CF_ZONE_ID=...
```

## End-to-end deploy

```bash
# 1. Create Cloudflare CNAME
python scripts/cf_dns_sv14.py

# 2. First-time deploy — runs setup-sv14.sh + setup-sv08.sh + first build
python scripts/deploy_lab_portal.py --target sv14   # ~ 5–10 min on first build
python scripts/deploy_lab_portal.py --target sv08   # ~ 1 min

# 3. Smoke test
python scripts/smoke_test_sv14.py --base https://sv14.bcse-vju.com
```

## Subsequent deploys (faster)

```bash
python scripts/deploy_lab_portal.py --target sv14 --skip-setup
# add --skip-build to only restart containers without rebuild
```

## Rollback

SSH onto SV14 manually and `git checkout <prev>` then re-run the deploy.
Or restore from `pg_dump` snapshot in `/opt/vju-lab-portal/postgres-backup/`.
