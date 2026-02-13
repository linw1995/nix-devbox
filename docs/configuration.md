# devbox.yaml Configuration

**English** | [简体中文](configuration.zh-CN.md)

`devbox.yaml` defines runtime parameters for Docker containers.

## Full Configuration Example

```yaml
run:
  # Security options
  security:
    read_only: false
    no_new_privileges: true
    cap_drop: ["ALL"]
    cap_add: []

  # Resource limits
  resources:
    memory: "1g"
    cpus: "2.0"
    pids_limit: 100

  # Logging
  logging:
    driver: "json-file"
    options:
      max-size: "10m"
      max-file: "3"

  # Network & ports
  ports:
    - "3000:3000"
    - "8080:8080"

  # Volume mounts (environment variables supported)
  # Note: /build and its subpaths are reserved for Nix internal use.
  volumes:
    - "$HOME/.config:/root/.config"

  # tmpfs mounts
  tmpfs:
    - "/tmp:size=100m,mode=1777"

  # Environment variables
  env:
    - "TERM=xterm-256color"

  # Extra arguments
  extra_args:
    - "--rm"
    - "--hostname=$HOSTNAME-devbox"
```

## Shell Variable Expansion

All configuration values support shell variable expansion (`$VAR`, `${VAR}`, `$(command)`) and are expanded by your shell when executing `docker run`:

```yaml
run:
  volumes:
    - "$HOME/.config:/root/.config"
    - "$(pwd):/workspace"
  env:
    - "BUILD_TIME=$(date -Iseconds)"
    - "USER=$USER"
```

**How it works**: nix-devbox builds a shell command and executes it via `$SHELL -c`, allowing your shell to perform variable expansion and command substitution.

### Escaping Literals

To use a literal `$` character without expansion, escape it with `\$`:

```yaml
run:
  tmpfs:
    # The path will be /$bunfs (literal $), not expanded
    - "/\\$bunfs:exec,mode=1777"
```

## Multi-Config Merge

When running multiple projects, configurations are merged automatically:

```bash
nix-devbox run ./project1 ./project2
```

| Type | Merge Strategy |
|------|----------------|
| Scalar (memory) | Override (later wins) |
| Boolean | Logical OR |
| List (ports, env) | Concatenate & dedupe |
| volumes/tmpfs | Override by **path** |

### Merge Example

```yaml
# project1/devbox.yaml
run:
  resources:
    memory: 512m
  volumes:
    - ./data:/app/data

# project2/devbox.yaml
run:
  resources:
    memory: 1g
  volumes:
    - ./data:/app/data
    - ./cache:/app/cache
```

Result:
- `memory: 1g` (overridden)
- `volumes: [./data:/app/data (proj2), ./cache:/app/cache]`
