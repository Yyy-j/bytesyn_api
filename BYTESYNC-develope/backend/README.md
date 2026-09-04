# BYTESYNC backend

Minimal FastAPI service with a PostgreSQL-backed health check.

## Configuration

Create the local environment file and add the real database password. Never
commit `.env`.

```sh
cd /path/to/BYTESYNC-develope/backend
cp .env.example .env
chmod 600 .env
```

Set `DATABASE_PASSWORD` in `.env`. Find the existing network used by PostgreSQL:

```sh
docker inspect bytesync-postgres --format '{{range $name, $_ := .NetworkSettings.Networks}}{{$name}}{{"\n"}}{{end}}'
```

If the command prints more than one network, choose one on which the container
name `bytesync-postgres` is resolvable by other containers. Put its exact name in
`.env` as `BYTESYNC_NETWORK`.

## Run and verify

```sh
docker compose up -d --build
docker compose ps
curl --fail-with-body http://192.168.3.2:8000/health
```

A successful response is:

```json
{"status":"ok","database":true}
```

If startup or the health check fails, inspect the API logs without exposing the
contents of `.env`:

```sh
docker compose logs --tail=100 api
```

The health endpoint returns HTTP 503 with a generic message when configuration
is missing or PostgreSQL cannot be reached. It does not return credentials,
connection strings, or tracebacks.
