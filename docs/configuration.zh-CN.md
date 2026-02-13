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

## 工作目录配置

运行 nix-devbox 时，它会自动从**当前工作目录**（你运行命令的目录）加载 `devbox.yaml`，并具有**最高优先级**。

这允许你在不修改远程 flake 的情况下覆盖其配置：

```bash
# 使用 registry flake，但用本地 devbox.yaml 覆盖配置
nix-devbox run @nix-devbox/base
```

```yaml
# ./devbox.yaml（在你的项目根目录）
run:
  resources:
    memory: 2g  # 覆盖远程 flake 的内存限制
  ports:
    - "8080:8080"  # 添加额外端口
  volumes:
    - ".:/workspace"  # 挂载当前项目
```

### 配置合并优先级

配置按以下顺序合并（后面的覆盖前面的）：

1. 第一个 flake 的 `devbox.yaml`
2. 第二个 flake 的 `devbox.yaml`
3. ...（后续 flakes）
4. **当前工作目录的 `devbox.yaml`**（最高优先级）

这在以下场景很有用：
- 覆盖共享 flake 的资源限制
- 添加项目特定的卷挂载
- 为本地开发配置端口
- 设置针对你特定环境的环境变量

## Registry（注册表）

`registry` 部分允许你定义常用 flake URL 的简短别名。

### 默认注册表

以下注册表是内置的：

| 名称 | URL |
|------|-----|
| `nix-devbox` | `github:linw1995/nix-devbox?dir=examples/` |

### 使用 Registry 引用

使用 `@name/path` 语法引用已注册的 flake：

```bash
# 等价于：github:linw1995/nix-devbox?dir=examples/base
nix-devbox run @nix-devbox/base

# 等价于：github:linw1995/nix-devbox?dir=examples/opencode
nix-devbox run @nix-devbox/opencode

# 混合使用 registry 和普通引用
nix-devbox run @nix-devbox/base . @other/repo
```

### 自定义 Registry

在 `devbox.yaml` 中定义你自己的 registry 条目：

```yaml
registry:
  myrepo: github:mycompany/flakes?dir=dev/
  internal: github:mycompany/internal-flakes

# 然后使用：
# nix-devbox run @myrepo/project
# nix-devbox run @internal/tools
```

**注意**：自定义 registry 条目会覆盖同名的内置 registry。

## Extends（继承）

`extends` 字段允许你声明依赖的其他 flake，在运行 `nix-devbox run .` 或 `nix-devbox build .` 时自动合并。

### 基本用法

```yaml
# devbox.yaml
extends:
  - @nix-devbox/base
  - @nix-devbox/opencode

run:
  resources:
    memory: 2g
```

运行：
```bash
nix-devbox run .
```

等价于：
```bash
nix-devbox run @nix-devbox/base @nix-devbox/opencode .
```

### 工作原理

1. **先解析 extends** - `extends` 中的所有 registry 引用被展开为完整 URL
2. **追加当前目录** - `.`（当前目录）自动添加到最后
3. **合并配置** - 所有 devbox.yaml 配置按顺序合并：
   1. 第一个继承的 flake 配置
   2. 第二个继承的 flake 配置
   3. ...（后续 extends）
   4. **当前目录的配置**（最高优先级）

### 使用场景

**项目配置，无需长命令：**
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
# 简单命令，复杂环境
nix-devbox run .
```

**与 CLI flakes 组合：**
```bash
# extends 自动添加
nix-devbox run . /path/to/another/flake
# 等价于：nix-devbox run @extends1 @extends2 . /path/to/another/flake
```

**混合 registry 和普通引用：**
```yaml
extends:
  - @nix-devbox/base
  - github:other/user/repo?dir=tools
```
