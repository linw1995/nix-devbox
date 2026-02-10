# nix-devbox

**简体中文** | [English](README.md)

合并多个 flake devShell，构建 Docker 镜像并运行容器。

## 安装

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
```

## 命令选项

| 选项 | 说明 |
|------|------|
| `-o, --output name:tag` | 镜像名称标签 |
| `-p, --port` | 端口映射 |
| `-V, --volume` | 卷挂载 |
| `-e, --env` | 环境变量 |
| `-w, --workdir` | 工作目录 |
| `--rebuild` | 强制重新构建 |
| `--dry-run` | 模拟运行 |
| `-v, --verbose` | 详细输出 |

## 依赖

- Python >= 3.9
- Nix (flakes)
- Docker
