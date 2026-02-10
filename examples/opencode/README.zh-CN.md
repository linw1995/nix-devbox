# Opencode 示例

**简体中文** | [English](README.md)

在容器化环境中运行 [Opencode](https://opencode.ai/) AI 编程助手的示例。

## 特性

- 隔离的 opencode 配置
- 通过卷挂载持久化数据
- tmpfs 用于临时文件

## 使用

```bash
# 构建并运行
nix-devbox run .

# 带自定义参数
nix-devbox run . -- /path/to/project
```

## 文件

- `flake.nix` - 包含 opencode 包的 Nix flake
- `devbox.yaml` - 容器运行时配置

## 配置说明

参见 [docs/configuration.zh-CN.md](../../docs/configuration.zh-CN.md)。
