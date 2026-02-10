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

## 配置文件

你可以在项目中创建 `devbox.yaml` 文件来定义 `docker run` 的推荐参数：

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
    - "$HOME/.config:/root/.config"  # 支持环境变量
    - "${PWD}/data:/data"
  extra_args:
    - "--rm"
    - "--label=user=$USER"
```

### 环境变量支持

`volumes`、`tmpfs` 和 `extra_args` 支持使用 `$VAR` 或 `${VAR}` 语法展开环境变量：

```yaml
volumes:
  - "$HOME/.ssh:/root/.ssh"
  - "${XDG_CONFIG_HOME}/git:/root/.config/git"
tmpfs:
  - "/tmp/$USER-cache:size=100m"
extra_args:
  - "--hostname=$HOSTNAME-devbox"
```

查看 [docs/configuration.zh-CN.md](docs/configuration.zh-CN.md) 获取完整配置说明。

## 示例

- [examples/base](examples/base/) - 基础配置示例
- [examples/opencode](examples/opencode/) - Opencode AI 助手配置

所有示例参见 [examples/README.zh-CN.md](examples/README.zh-CN.md)。

## 依赖

- Python >= 3.9
- Nix (flakes)
- Docker
