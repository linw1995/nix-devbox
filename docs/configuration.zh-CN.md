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
  volumes:
    - ".:/workspace"
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

## 环境变量

- `$VAR` 或 `${VAR}` 语法
- `$$VAR` 表示字面量 `$VAR`（不展开）
- 支持字段：`volumes`, `tmpfs`, `extra_args`

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
