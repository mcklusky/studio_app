# Operator runbook: Just Smile Empire Business Manager

For the person who installs and looks after the server. Commands are run from the repository root on the server.

## 1. What runs where

| Container | Purpose | Data it keeps |
|---|---|---|
| `web` (Caddy) | HTTPS certificates, security headers, serves the app, forwards `/api/` to the backend | `caddy_data` (certificates) |
| `backend` (Django + gunicorn) | All business rules and the API. Applies database migrations on start | none (stateless) |
| `db` (PostgreSQL 17) | All records | `postgres_data` volume |
| `backup` | A backup at start-up, then daily at `BACKUP_HOUR` | writes to `BACKUP_DIR` (default `deploy/backups/`) |

Uploaded receipt photos and product images live in the `private_media` volume. **The database and `private_media` together are the business's records.** Back up both.

## 2. First installation

1. Prepare a Linux server (2 GB RAM is enough to start) with Docker and the Docker Compose plugin. Open ports 80 and 443 only.
2. Point the domain's DNS (an `A` record such as `app.justsmileempire.com`) at the server's public IP.
3. Copy the repository to the server, then run:
   ```sh
   cp deploy/.env.example deploy/.env
   python3 -c "import secrets; print(secrets.token_urlsafe(50))"   # run twice: DJANGO_SECRET_KEY, POSTGRES_PASSWORD
   nano deploy/.env                                                  # set SITE_DOMAIN and the two secrets
   chmod 600 deploy/.env
   docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env up -d --build
   ```
4. Create the organization and its first owner:
   ```sh
   C="docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env"
   $C exec backend python manage.py createsuperuser          # choose the owner's username and a strong password
   $C exec backend python manage.py setup_organization --name "Just Smile Empire" --admin-username <that username>
   ```
5. Open `https://<SITE_DOMAIN>`, sign in as the owner, enter today's LRD rate, and add staff from **Team & access**.
6. Optional: load the opening products and stock. See [the admin guide](../onboarding/admin-guide.md#opening-products-and-stock).
7. Set up uptime monitoring (section 6) and off-site backup copies (section 4) **before** staff start using the system.

## 3. Updating to a new version

```sh
git pull
docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env exec backup sh /scripts/backup-now.sh   # backup first
docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env up -d --build
docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env exec backend python manage.py verify_integrity
```
Migrations run automatically when the backend starts. Update outside business hours; staff see an error for a few seconds while the backend restarts.

## 4. Backups

* **Automatic:** the `backup` container makes `BACKUP_DIR/<yyyymmdd-hhmm>/` with `database.dump`, `private_media.tar.gz` and `SHA256SUMS`, and deletes folders older than `BACKUP_RETENTION_DAYS` (default 30).
* **On demand:** `docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env exec backup sh /scripts/backup-now.sh`
* **Check it is working:** `cat deploy/backups/LATEST` should show today's date. `docker compose ... logs backup` shows each run.
* **Off-site copy (required):** a backup on the same server is lost with the server. At least weekly, copy the newest folder to a second location: an encrypted USB drive kept away from the shop, or cloud storage (e.g. `rclone copy deploy/backups remote:justsmile-backups`). Backups contain customer names and phone numbers; keep copies encrypted and access-controlled.

## 5. Restoring (and the monthly restore drill)

```sh
sh deploy/backup/restore.sh deploy/backups/20261124-0100
```
The script checks the checksums, asks you to type `RESTORE`, stops the app, replaces the database and uploads, starts the app, and runs `manage.py verify_integrity`. That check compares stock balances with the movement ledger, payments with what they paid off, sale totals with their lines, and confirms every uploaded file exists. It must end with **"All checks passed"**.

**Drill once a month, on a spare machine or a copy of the server, never on the live system:** restore last night's backup, run the check, sign in, and spot-check today's sales total, one customer statement and one receipt photo. Record the date and result in the table below. A backup that has never been restored is not proven to work.

| Date | Backup restored | verify_integrity | Spot checks | By |
|---|---|---|---|---|
| | | | | |

## 6. Monitoring

* **Uptime:** point a free uptime monitor (e.g. UptimeRobot, Better Stack) at `https://<SITE_DOMAIN>/api/v1/health/ready/`. It returns 200 only when the database answers and upload storage is writable, otherwise 503.
* **Error emails:** set `DJANGO_ADMINS` and the `EMAIL_*` settings in `deploy/.env`. Server errors are then emailed with their request ID.
* **Logs:** `docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env logs --tail=200 backend`. Every line carries `[req <id>]`. When staff report an error they see a "Reference: abcd1234". Search the logs for it: `... logs backend | grep abcd1234`.
* **Disk space:** check monthly with `df -h` and `du -sh deploy/backups`.

## 7. Security housekeeping

* `deploy/.env` holds the secrets: `chmod 600`, never commit it, never send it by chat or email.
* After HTTPS has worked for a few days, set `HSTS_SECONDS=31536000` and run `up -d` again.
* Optionally move the admin site: set `DJANGO_ADMIN_PATH` to an unguessable word. Day-to-day work never needs the Django admin.
* Apply OS security updates monthly. Rebuild the images (`up -d --build --pull always`) monthly for base-image fixes.
* When someone leaves, deactivate them in **Team & access** the same day. If they knew server or database passwords, rotate `POSTGRES_PASSWORD` and `DJANGO_SECRET_KEY`. Rotating the secret key signs everyone out.
* Integrity check any time: `docker compose ... exec backend python manage.py verify_integrity`.

## 8. Troubleshooting

| Symptom | Check |
|---|---|
| Site not reachable | `docker compose ... ps`; DNS points to the server; ports 80/443 open |
| Certificate errors | `docker compose ... logs web`; DNS must resolve to this server before Caddy can obtain a certificate |
| "Something went wrong. Reference: …" | Search backend logs for the reference |
| Health check says `database: unavailable` | `docker compose ... logs db`; disk full? |
| Health check says `storage: unavailable` | The `private_media` volume is full or read-only |
| LRD sales blocked | An owner must enter today's rate (the alert bell shows this) |
| Staff locked out after 5 wrong passwords | Wait one minute (login is rate-limited), or reset their password in **Team & access** |
