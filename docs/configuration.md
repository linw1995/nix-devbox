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

## Working Directory Config

When running nix-devbox, it automatically loads `devbox.yaml` from your **current working directory** (where you run the command) with the **highest priority**.

This allows you to override configurations from remote flakes without modifying them:

```bash
# Use registry flake but override with local devbox.yaml
nix-devbox run @nix-devbox/base
```

```yaml
# ./devbox.yaml (in your project root)
run:
  resources:
    memory: 2g  # Override remote flake's memory limit
  ports:
    - "8080:8080"  # Add additional ports
  volumes:
    - ".:/workspace"  # Mount current project
```

### Config Merge Priority

Configurations are merged in this order (later overrides earlier):

1. First flake's `devbox.yaml`
2. Second flake's `devbox.yaml`
3. ... (subsequent flakes)
4. **Current working directory's `devbox.yaml`** (highest priority)

This is useful for:
- Overriding resource limits from shared flakes
- Adding project-specific volume mounts
- Configuring ports for local development
- Setting environment variables for your specific setup

## Registry

The `registry` section allows you to define short aliases for frequently used flake URLs.

### Default Registry

The following registry is built-in:

| Name | URL |
|------|-----|
| `nix-devbox` | `github:linw1995/nix-devbox?dir=examples/` |

### Using Registry References

Use `@name/path` syntax to reference registered flakes:

```bash
# Equivalent to: github:linw1995/nix-devbox?dir=examples/base
nix-devbox run @nix-devbox/base

# Equivalent to: github:linw1995/nix-devbox?dir=examples/opencode
nix-devbox run @nix-devbox/opencode

# Mix registry and regular references
nix-devbox run @nix-devbox/base . @other/repo
```

### Custom Registry

Define your own registry entries in `devbox.yaml`:

```yaml
registry:
  myrepo: github:mycompany/flakes?dir=dev/
  internal: github:mycompany/internal-flakes

# Then use them:
# nix-devbox run @myrepo/project
# nix-devbox run @internal/tools
```

**Note**: Custom registry entries override built-in ones if they have the same name.

## Extends

The `extends` field allows you to declare dependencies on other flakes that should be merged automatically when running `nix-devbox run .` or `nix-devbox build .`.

### Basic Usage

```yaml
# devbox.yaml
extends:
  - @nix-devbox/base
  - @nix-devbox/opencode

run:
  resources:
    memory: 2g
```

When you run:
```bash
nix-devbox run .
```

It is equivalent to:
```bash
nix-devbox run @nix-devbox/base @nix-devbox/opencode .
```

### How It Works

1. **Extends are resolved first** - All registry references in `extends` are expanded to full URLs
2. **Current directory is appended** - The `.` (current directory) is automatically added at the end
3. **Configs are merged** - All devbox.yaml configurations are merged in order:
   1. First extended flake's config
   2. Second extended flake's config
   3. ... (subsequent extends)
   4. **Current directory's config** (highest priority)

### Use Cases

**Project setup without long command lines:**
```yaml
# devbox.yaml
extends:
  - @nix-devbox/python
  - @nix-devbox/nodejs

run:
  ports:
    - "3000:3000"
    - "8000:8000"
```
```bash
# Simple command, complex environment
nix-devbox run .
```

**Combining with CLI flakes:**
```bash
# Extends are automatically added
nix-devbox run . /path/to/another/flake
# Equivalent to: nix-devbox run @extends1 @extends2 . /path/to/another/flake
```

**Mixing registry and regular references:**
```yaml
extends:
  - @nix-devbox/base
  - github:other/user/repo?dir=tools
```
