
# VPS Deployment with Docker Compose and Nginx

This guide describes how to deploy independent instances of this template on a single VPS using:

- Docker Compose for application containers.
- PostgreSQL for each application's database.
- Nginx as a shared reverse proxy.
- URL prefixes to expose multiple applications through a single public port.
- `ROOT_PATH` to support applications hosted under a URL prefix.

## 1. Architecture

All applications share the same Nginx instance and public port. Each application runs in its own Docker Compose project, with independent containers, database volumes, environment variables, and backend port.

Example:

```text
Internet
   |
   v
VPS:8002
   |
   v
Nginx (shared)
   |
   +-- /                         -> 127.0.0.1:8001
   |
   +-- /apicanta/                -> 127.0.0.1:8003
   |
   +-- /another-challenge/       -> 127.0.0.1:8004
```

Example directory structure:

```text
/var/www/
├── edn/
├── interviewier/
└── challenge/
    ├── thc-python-fa/
    ├── apicanta/
    └── another-challenge/
```

The template itself can also run as an application, independently of the challenges created from it.

### Deployment principles

- Each challenge has its own Git repository.
- Each challenge has its own `.env` file.
- Each challenge has its own Docker Compose project name.
- Each challenge has its own PostgreSQL container and persistent volume.
- Backend ports are bound to `127.0.0.1`, never directly exposed to the Internet.
- Nginx is the only public entry point for these applications.
- The application source code does not contain VPS-specific Nginx configuration.

## 2. VPS Requirements

The VPS must have:

- Linux (Ubuntu recommended).
- Docker Engine.
- Docker Compose V2.
- Nginx.
- Git.

Verify Docker and Compose:

```bash
docker --version
docker compose version
```

Verify Nginx:

```bash
nginx -v
```

## 3. Create the Application Directory

For each new challenge, create an independent directory.

Example:

```bash
sudo mkdir -p /var/www/challenge/apicanta
sudo chown "$USER":"$USER" /var/www/challenge/apicanta
```

Clone the challenge repository:

```bash
cd /var/www/challenge/apicanta

git clone https://github.com/YOUR_USERNAME/apicanta.git .
```

The repository must contain the template's application files and its Docker Compose configuration.

## 4. Configure Environment Variables

Create the environment file:

```bash
cp .env.example .env
```

Configure the required application variables and generate unique secrets for this instance.

Generate secure values:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

Use separate generated values for:

- `SECRET_KEY`
- `POSTGRES_PASSWORD`
- `FIRST_SUPERUSER_PASSWORD`

Configure the initial administrator:

```env
FIRST_SUPERUSER=admin@example.com
```

### Deployment-specific variables

In addition to the variables documented in `.env.example`, configure:

```env
ROOT_PATH=/apicanta

BACKEND_HOST_PORT=8003

FRONTEND_HOST=http://YOUR_SERVER_IP:8002/apicanta
```

Replace the example values according to the application.

| Variable | Description |
|---|---|
| `ROOT_PATH` | Public URL prefix, without a trailing slash |
| `BACKEND_HOST_PORT` | Unique local backend port |
| `FRONTEND_HOST` | Public application URL, including its prefix |

For example:

```text
Application URL: http://178.238.237.209:8002/apicanta/
ROOT_PATH:       /apicanta
Backend port:    8003
```

**Important:**

- Never reuse secrets between challenges.
- Never commit `.env`.
- Do not expose PostgreSQL or backend ports publicly.
- Use a unique backend port for every challenge.
- Keep the `ROOT_PATH` value consistent with the Nginx route.

## 5. Configure Docker Compose for the VPS

The repository contains shared configuration and local development overrides.

For this VPS architecture, use an additional file named:

`compose.vps.yml`

This file contains only the VPS-specific settings.

Example:

```yaml
services:
  proxy:
    profiles:
      - traefik

  adminer:
    profiles:
      - adminer

  db:
    restart: unless-stopped

  backend:
    restart: unless-stopped
    ports:
      - "127.0.0.1:${BACKEND_HOST_PORT:?Variable not set}:8000"
    environment:
      FRONTEND_HOST: ${FRONTEND_HOST:?Variable not set}
```

This configuration:

- Disables the bundled Traefik service.
- Disables Adminer on the VPS.
- Restarts the database and backend automatically.
- Publishes the backend only on the local loopback interface.
- Passes the public application URL to FastAPI.

The base `compose.yml` already passes `ROOT_PATH` to the backend.

The deployment commands must explicitly use `compose.yml` and `compose.vps.yml`. This prevents Docker Compose from automatically loading `compose.override.yml`, which is intended for local development.

## 6. Validate the Configuration

From the application directory:

```bash
docker compose --env-file .env -p apicanta \
  -f compose.yml \
  -f compose.vps.yml \
  config --quiet
```

The command should finish without errors.

Replace `apicanta` with the actual Compose project name when deploying another challenge.

## 7. Build and Initialize the Application

Build the backend image:

```bash
docker compose --env-file .env -p apicanta \
  -f compose.yml \
  -f compose.vps.yml \
  build backend
```

Run the initialization script:

```bash
docker compose --env-file .env -p apicanta \
  -f compose.yml \
  -f compose.vps.yml \
  run --rm backend bash scripts/prestart.sh
```

The `prestart.sh` script:

1. Runs Alembic migrations.
2. Creates the initial application data and administrator account.

The database is started through the backend service dependency.

## 8. Start the Application

Start the application:

```bash
docker compose --env-file .env -p apicanta \
  -f compose.yml \
  -f compose.vps.yml \
  up -d
```

Check the containers:

```bash
docker compose --env-file .env -p apicanta \
  -f compose.yml \
  -f compose.vps.yml \
  ps
```

Both the backend and database should become healthy.

Check the backend logs:

```bash
docker compose --env-file .env -p apicanta \
  -f compose.yml \
  -f compose.vps.yml \
  logs -f backend
```

## 9. Configure Nginx

Nginx is shared by all challenges.

The main configuration is:

```text
/etc/nginx/sites-available/fastapi.conf
```

It listens on the public port and includes the configuration files for individual challenges:

```nginx
server {
    listen 8002;
    listen [::]:8002;

    server_name _;

    include /etc/nginx/challenge-locations/*.conf;

    location / {
        proxy_pass http://127.0.0.1:8001;
        proxy_http_version 1.1;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

This configuration should be created once.

Do not modify the main Nginx configuration every time a new challenge is deployed.

### Create a configuration file for each challenge

Challenge-specific location files are stored outside the application repositories:

```text
/etc/nginx/
├── sites-available/
│   └── fastapi.conf
│
└── challenge-locations/
    ├── apicanta.conf
    └── another-challenge.conf
```

For ApiCanta, create:

`/etc/nginx/challenge-locations/apicanta.conf`

```nginx
location = /apicanta {
    return 301 /apicanta/;
}

location /apicanta/ {
    proxy_pass http://127.0.0.1:8003/;
    proxy_http_version 1.1;

    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

**Important:** The trailing slash in `proxy_pass` is intentional.

Nginx removes the `/apicanta/` prefix before forwarding the request to the backend.

For example:

```text
Public request:
  /apicanta/api/v1/utils/health-check/

Request received by FastAPI:
  /api/v1/utils/health-check/
```

FastAPI uses `ROOT_PATH=/apicanta` to understand its external URL.

### Validate and reload Nginx

Validate the configuration:

```bash
sudo nginx -t
```

If the configuration is valid, reload Nginx:

```bash
sudo systemctl reload nginx
```

## 10. Verify the Deployment

Check the backend directly from the VPS:

```bash
curl -i http://127.0.0.1:8003/api/v1/utils/health-check/
```

Expected response:

```text
HTTP/1.1 200 OK
```

Check the public application:

```bash
curl -I http://YOUR_SERVER_IP:8002/apicanta/
```

Open the application:

```text
http://YOUR_SERVER_IP:8002/apicanta/
```

Open Swagger UI:

```text
http://YOUR_SERVER_IP:8002/apicanta/docs
```

Verify that:

- The frontend loads correctly.
- Static assets load under the application prefix.
- API requests include the correct prefix externally.
- Authentication and navigation work.
- Refreshing a frontend route works.
- Swagger UI uses the correct API paths.

## 11. Deploying Another Challenge

To deploy another challenge, repeat the same process with unique values.

Example:

| Setting | ApiCanta | Another Challenge |
|---|---|---|
| Compose project | `apicanta` | `another-challenge` |
| Directory | `/var/www/challenge/apicanta` | `/var/www/challenge/another-challenge` |
| URL prefix | `/apicanta` | `/another-challenge` |
| Backend port | `8003` | `8004` |
| ROOT_PATH | `/apicanta` | `/another-challenge` |
| Nginx file | `apicanta.conf` | `another-challenge.conf` |

Each challenge has its own containers and database volume.

Only its own Nginx location file needs to be added. The main Nginx configuration remains unchanged.

## 12. Updating an Existing Challenge

To update the application after pushing changes to its repository:

```bash
cd /var/www/challenge/apicanta

git pull origin main
```

Validate the Compose configuration:

```bash
docker compose --env-file .env -p apicanta \
  -f compose.yml \
  -f compose.vps.yml \
  config --quiet
```

Build the updated image:

```bash
docker compose --env-file .env -p apicanta \
  -f compose.yml \
  -f compose.vps.yml \
  build backend
```

Run database migrations and initialization:

```bash
docker compose --env-file .env -p apicanta \
  -f compose.yml \
  -f compose.vps.yml \
  run --rm backend bash scripts/prestart.sh
```

Apply the updated application:

```bash
docker compose --env-file .env -p apicanta \
  -f compose.yml \
  -f compose.vps.yml \
  up -d
```

Check the application:

```bash
docker compose --env-file .env -p apicanta \
  -f compose.yml \
  -f compose.vps.yml \
  ps
```

## 13. Stop or Remove a Challenge

Stop and remove the containers:

```bash
docker compose --env-file .env -p apicanta \
  -f compose.yml \
  -f compose.vps.yml \
  down
```

This preserves named database volumes.

To permanently remove the challenge:

1. Remove its Nginx location file.
2. Validate and reload Nginx.
3. Stop its Docker Compose project.
4. Remove its application directory if no longer needed.
5. Remove its database volume only if its data is no longer needed.

**Warning:** The following command permanently deletes the project's Compose-managed volumes, including its database data:

```bash
docker compose --env-file .env -p apicanta \
  -f compose.yml \
  -f compose.vps.yml \
  down -v
```

Use it only when the database data is intentionally being discarded.

## 14. Operational Notes

- Each application must have a unique Compose project name.
- Each application must have a unique host backend port.
- Backend ports must bind to `127.0.0.1`.
- PostgreSQL must not be published publicly.
- Keep production `.env` files on the VPS only.
- Use separate credentials for each challenge.
- Do not use `docker compose down -v` during routine deployments.
- Monitor VPS CPU, RAM, and disk usage when running multiple applications.
- This deployment guide describes manual deployment. Automatic deployment through GitHub Actions requires separate CI/CD configuration.
