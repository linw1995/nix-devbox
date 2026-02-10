# Base Example

**简体中文** | [English](README.md)

基础 nix-devbox 示例，展示 `devbox.yaml` 配置用法。

## 文件

- `flake.nix` - Nix flake 定义
- `devbox.yaml` - 运行时配置

## 使用

```bash
# 构建镜像
nix-devbox build .

# 运行容器（使用配置）
nix-devbox run .

# 查看 docker 命令
nix-devbox run . --dry-run
```

## 配置说明

参见 [docs/configuration.md](../../docs/configuration.md)。
