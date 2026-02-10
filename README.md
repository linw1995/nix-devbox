# nix-devbox

**English** | [简体中文](README.zh-CN.md)

Merge multiple flake devShells, build Docker images, and run containers.

## Installation

```bash
uv venv
uv pip install -e .
```

## Usage

```bash
# Build image
nix-devbox build /path/to/project

# Run container (auto-builds if needed)
nix-devbox run /path/to/project

# Merge multiple devShells
nix-devbox build /path/to/proj1 /path/to/proj2#nodejs
```

## Command Options

| Option | Description |
|--------|-------------|
| `-o, --output name:tag` | Image name and tag |
| `-p, --port` | Port mapping |
| `-V, --volume` | Volume mount |
| `-e, --env` | Environment variable |
| `-w, --workdir` | Working directory |
| `--rebuild` | Force rebuild |
| `--dry-run` | Dry run (show commands only) |
| `-v, --verbose` | Verbose output |

## Configuration File

You can create a `devbox.yaml` file in your project to define recommended `docker run` options for devshell environments:

```yaml
run:
  security:
    no_new_privileges: true
    cap_drop: ["ALL"]
  resources:
    memory: "1g"
    cpus: "2.0"
  logging:
    driver: "json-file"
    options:
      max-size: "10m"
  tmpfs:
    - "/tmp:size=100m,mode=1777"
    - "/var/cache:size=50m"
  volumes:
    - "$HOME/.config:/root/.config"  # Environment variables supported
    - "${PWD}/data:/data"
  extra_args:
    - "--rm"
    - "--label=user=$USER"
```

### Environment Variables

`volumes`, `tmpfs`, and `extra_args` support environment variable expansion using `$VAR` or `${VAR}` syntax:

```yaml
volumes:
  - "$HOME/.ssh:/root/.ssh"
  - "${XDG_CONFIG_HOME}/git:/root/.config/git"
tmpfs:
  - "/tmp/$USER-cache:size=100m"
extra_args:
  - "--hostname=$HOSTNAME-devbox"
```

See [docs/configuration.md](docs/configuration.md) for complete configuration reference.

## Examples

- [examples/base](examples/base/) - Basic configuration example
- [examples/opencode](examples/opencode/) - Opencode AI agent setup

See [examples/README.md](examples/README.md) for all examples.

## Dependencies

- Python >= 3.9
- Nix (with flakes)
- Docker
