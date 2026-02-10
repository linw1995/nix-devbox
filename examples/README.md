# Examples

**English** | [简体中文](README.zh-CN.md)

Example projects demonstrating nix-devbox usage.

## Layered Structure

```
┌─────────────────────────────────────────────────────────┐
│  Layer 3: Your Project                                  │
│  └── stacked-example/                                   │
│      → Overrides memory, adds ports                     │
└─────────────────────────────────────────────────────────┘
                         ▲ merges with
┌─────────────────────────────────────────────────────────┐
│  Layer 2: Application                                   │
│  └── opencode/      → AI agent with persistence        │
└─────────────────────────────────────────────────────────┘
                         ▲ builds on
┌─────────────────────────────────────────────────────────┐
│  Layer 1: Foundation                                    │
│  └── base/          → Common devshell options          │
└─────────────────────────────────────────────────────────┘
```

| Example | Layer | Description |
|---------|-------|-------------|
| [base](base/) | 1 | Security, resources, logging, tmpfs |
| [opencode](opencode/) | 2 | Volume mounts, env vars, `$$` escape |
| [stacked-example](stacked-example/) | 3 | Shows how to layer configs |

See [docs/configuration.md](../docs/configuration.md) for details.
