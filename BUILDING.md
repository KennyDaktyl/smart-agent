# Building Smart Agent Images

## Summary

The Docker image should contain only application code and dependencies.
Machine-specific configuration must stay outside the image and be mounted on the target host.

These local files are intentionally excluded from the Docker build context:

- `.env`
- `config.json`
- `hardware_config.json`

This is controlled by `.dockerignore`.

## Dockerfile Targets

The current `Dockerfile` defines these stages:

- `builder`
- `runtime`
- `dev`

There is no `prod` stage in the current file.

For production builds, use the `runtime` target.

## Build Production Image

Run from the `smart-agent` directory:

```bash
docker build --target runtime -t docker.io/kennydaktyl/smart-agent:agent_v1.0.6 .
```

Example with a different tag:

```bash
docker build --target runtime -t docker.io/kennydaktyl/smart-agent:agent_v1.0.7 .
```

## Push Image

```bash
docker push docker.io/kennydaktyl/smart-agent:agent_v1.0.6
```

## Run On Target Host

The target machine should provide its own local files:

- `.env`
- `config.json`
- `hardware_config.json`

Example compose service:

```yaml
services:
  agent:
    image: docker.io/kennydaktyl/smart-agent:agent_v1.0.6
    restart: unless-stopped
    network_mode: host
    volumes:
      - ./.env:/app/.env:rw
      - ./config.json:/app/config.json:rw
      - ./hardware_config.json:/app/hardware_config.json:rw
      - ./logs:/app/logs:rw
    env_file:
      - .env
```

## Important Notes

- Do not build with `--target prod` unless a `prod` stage is added to the Dockerfile.
- If you are already inside the `smart-agent` directory, use `.` as the build context.
- Correct:

```bash
docker build --target runtime -t docker.io/kennydaktyl/smart-agent:agent_v1.0.6 .
```

- Incorrect:

```bash
docker build --target runtime -t docker.io/kennydaktyl/smart-agent:agent_v1.0.6 smart-agent
```

## Optional Improvement

If you want to keep using `--target prod`, add this to the Dockerfile:

```dockerfile
FROM runtime AS prod

FROM runtime AS dev
```

Then production builds can use:

```bash
docker build --target prod -t docker.io/kennydaktyl/smart-agent:agent_v1.0.6 .
```
