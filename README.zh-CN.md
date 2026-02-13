# nix-devbox

**简体中文** | [English](README.md)

合并多个 flake devShell，构建 Docker 镜像并运行容器。

## 安装

```bash
uv tool install nix-devbox
```

### 开发

```bash
uv venv
uv pip install -e .
```

## 用法

```bash
# 构建镜像
nix-devbox build /path/to/project

# 运行容器（自动构建）
nix-devbox run /path/to/project

# 合并多个 devShell
nix-devbox build /path/to/proj1 /path/to/proj2#nodejs

# 从远程 GitHub 仓库构建
nix-devbox build github:owner/repo

# 从远程子目录构建
nix-devbox build "github:owner/repo?dir=dev"
```

查看 [docs/configuration.zh-CN.md](docs/configuration.zh-CN.md) 了解配置选项。

## 示例

参见 [examples/](examples/) 目录获取示例配置。

## 依赖

- Python >= 3.9
- Nix (flakes)
- Docker

## 许可证

MIT
