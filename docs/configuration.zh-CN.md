# devbox.yaml 配置

**简体中文** | [English](configuration.md)

`devbox.yaml` 定义 Docker 容器的运行时参数。

## 完整配置示例

```yaml
run:
  # 安全选项
  security:
    read_only: false
    no_new_privileges: true
    cap_drop: ["ALL"]
    cap_add: []

  # 资源限制
  resources:
    memory: "1g"
    cpus: "2.0"
    pids_limit: 100

  # 日志配置
  logging:
    driver: "json-file"
    options:
      max-size: "10m"
      max-file: "3"

  # 网络与端口
  ports:
    - "3000:3000"
    - "8080:8080"

  # 卷挂载（支持环境变量）
  # 注意：/build 及其子路径保留给 Nix 内部使用。
  volumes:
    - "$HOME/.config:/root/.config"

  # tmpfs 挂载
  tmpfs:
    - "/tmp:size=100m,mode=1777"

  # 环境变量
  env:
    - "TERM=xterm-256color"

  # 额外参数
  extra_args:
    - "--rm"
    - "--hostname=$HOSTNAME-devbox"
```

## Shell 变量展开

所有配置值都支持 shell 变量展开（`$VAR`、`${VAR}`、`$(command)`），由你的 shell 在执行 `docker run` 时展开：

```yaml
run:
  volumes:
    - "$HOME/.config:/root/.config"
    - "$(pwd):/workspace"
  env:
    - "BUILD_TIME=$(date -Iseconds)"
    - "USER=$USER"
```

**工作原理**：nix-devbox 构建 shell 命令并通过 `$SHELL -c` 执行，让你的 shell 执行变量展开和命令替换。

### 转义字面量

如需使用字面量 `$` 而不展开，请使用 `\$` 转义：

```yaml
run:
  tmpfs:
    # 路径将是 /$bunfs（字面量 $），不会被展开
    - "/\\$bunfs:exec,mode=1777"
```

## 多配置合并

| 类型 | 合并策略 |
|------|----------|
| 标量 (memory) | 后覆盖前 |
| 布尔 | 逻辑或 |
| 列表 (ports, env) | 合并去重 |
| volumes/tmpfs | 按**路径**覆盖 |

示例：
```bash
# project1 + project2 配置自动合并
nix-devbox run ./project1 ./project2
```
