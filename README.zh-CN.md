# nix-devbox

**简体中文** | [English](README.md)

将多个 flake devShell 合并为可复现的 Docker 镜像，打造一致的开发环境。

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

## 使用场景

### 为 AI Coding Agent 提供开发环境

为 AI 编程助手（如 Claude Code、OpenCode 等）提供安全、稳定、可复现的沙盒开发环境。

**核心优势：**

- **可复现的环境** - 所有会话使用完全相同的工具链版本
- **隔离的工作空间** - 每个项目在独立容器中运行，不会污染宿主系统
- **声明式配置** - 在 `flake.nix` 中定义所有依赖，无需手动安装
- **多语言支持** - 轻松组合不同技术栈的 devShell

**快速开始：**

```bash
# 1. 推荐：学习编写自己的 flake devShells
#    （参考：https://nix.dev/tutorials/first-steps/declarative-shell）
#    或者直接使用本项目提供的预置 devShells：
nix-devbox run @nix-devbox/base

# 2. 或为复杂项目堆叠多个 devShell
nix-devbox run @nix-devbox/base @nix-devbox/opencode

# 3. AI Agent 现在拥有干净、可复现的开发环境
# 所有工具已预装并配置完毕
```

如果你的项目有 `flake.nix`，可以追加 `.` 来使用它。如需项目特定的配置（环境变量、工作目录等），可在项目根目录创建 `devbox.yaml`。详见 [docs/configuration.zh-CN.md](docs/configuration.zh-CN.md)。

查看 [examples/stacked-example/](examples/stacked-example/) 获取完整的堆叠 devShell 配置示例。参考 [examples/opencode/](examples/opencode/) 中的 OpenCode Agent 配置，并贡献你自己的 Agent 示例！

## 示例

参见 [examples/](examples/) 目录获取示例配置。

## 依赖

- Python >= 3.9
- Nix (flakes)
- Docker

## 许可证

MIT
