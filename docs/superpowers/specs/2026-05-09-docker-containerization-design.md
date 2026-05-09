# Docker 封装部署设计

## 问题

当前项目通过宿主机 cron 直接执行 `scripts/run.sh`。这套方式在固定环境下可行，但在临时云服务器和后续可能迁移机器的场景里，运行稳定性依赖宿主机状态：

1. `uv`、Python 依赖和 Playwright Chromium 需要在宿主机正确安装。
2. cron 运行用户、PATH、`.env`、目录写权限和 Git 凭证都容易因环境差异出问题。
3. 切换服务器时，需要重复安装和排查运行时依赖。

用户希望用 Docker 封装该项目，以降低部署迁移和环境漂移带来的故障概率，同时保留现有定时任务和 Git 输出流程。

## 目标

1. 提供一个可在云服务器上稳定运行的 Docker 镜像。
2. 将 Python、`uv`、Playwright Chromium 及其系统依赖固化进镜像。
3. 继续使用宿主机 cron 触发任务，不在容器内额外维护 cron。
4. 保留现有 `scripts/run.sh` 作为主执行入口。
5. 保留容器内的日报生成、`git commit` 和 `git push` 流程。
6. 通过宿主提供 `.env`，继续使用 `GITHUB_PAT` 完成非交互式 Git 推送。
7. 让 `output/`、`logs/`、SQLite 数据库和 Git 仓库状态持久化在宿主机上，便于迁移和排障。

## 非目标

1. 不改成 Kubernetes、Nomad 或其他编排系统。
2. 不把 cron 调度迁入容器内部。
3. 不重构 `scripts/run.sh` 的整体抓取和汇总顺序。
4. 不在本次设计中拆分“生成内容”和“Git 发布”为两个独立服务。
5. 不把敏感凭证写入镜像或 Git 跟踪文件。

## 方案对比

### 方案 A：单镜像 + 宿主机 cron 执行 `docker run`（采用）

- 构建一个完整运行镜像，包含 Python、`uv`、项目依赖、Playwright Chromium 和系统库。
- 宿主机 cron 改为执行 `docker run --rm ...`。
- 宿主机挂载仓库目录，容器内直接执行现有 `scripts/run.sh`。
- `.env` 由宿主通过 `--env-file` 提供，Git 推送继续使用 `GITHUB_PAT`。

优点：

- 与当前 cron 模式最接近，迁移成本最低。
- 环境一致性强，换机时只需迁移仓库、`.env` 和 cron 配置。
- 容器生命周期清晰，日志和失败边界好排查。

缺点：

- Git、日志和 SQLite 都依赖宿主挂载目录权限配置正确。
- 需要在容器中额外处理非交互式 Git 认证。

### 方案 B：使用 `docker compose` 管理，再由宿主机 cron 调用

优点：

- 启动参数、挂载和环境变量更集中。
- 适合后续增加辅助服务时扩展。

缺点：

- 对当前单任务项目偏重。
- 仍然需要宿主机 cron，且比直接 `docker run` 多一层抽象。

### 方案 C：容器内运行 cron

优点：

- 理论上可以把调度也收进镜像。

缺点：

- 调试和日志分流更复杂。
- 不符合当前已经有宿主机调度的现实。
- 容器职责不清，排障体验更差。

## 最终设计

采用 **方案 A**：构建一个完整运行镜像，由宿主机 cron 定时执行 `docker run`，容器内继续执行现有 `scripts/run.sh`，并保留日报生成和 Git 推送流程。

设计原则是：**环境封进镜像，状态留在宿主机**。

## 详细设计

### 1. 运行架构

部署后责任划分如下：

- **Docker 镜像**
  - 提供统一的 Python 运行时。
  - 提供 `uv`、项目依赖、Playwright Chromium 和相关系统依赖。
  - 提供固定工作目录，例如 `/app`。

- **宿主机 cron**
  - 继续作为唯一调度入口。
  - 负责执行 `docker run --rm ...`。
  - 负责把宿主机的项目目录和 `.env` 提供给容器。

- **容器**
  - 启动后直接执行 `scripts/run.sh`。
  - 完成抓取、汇总、写入数据库、生成日报、`git commit`、`git push`。
  - 任务结束后退出，不保留常驻进程。

### 2. 文件和环境挂载

宿主机需要把整个仓库目录挂载进容器，而不是只挂 `output/`：

1. `scripts/run.sh` 依赖仓库内的脚本、`.git`、`output/`、`logs/`。
2. `git commit` 和 `git push` 需要访问实际工作树和 Git 元数据。
3. SQLite 文件 `output/octopus.db` 和缓存文件需要持久化在宿主机。

推荐挂载策略：

- 宿主 `/home/admin/octopus` 挂载到容器 `/app`
- 容器工作目录设置为 `/app`
- 宿主通过 `--env-file /home/admin/octopus/.env` 提供环境变量

这会保留以下状态：

- `output/daily/`
- `output/octopus.db`
- `output/zhihu_storage_state.json`
- `logs/`
- `.git/`

### 3. 镜像内容

`Dockerfile` 需要包含：

1. 官方 Python 基础镜像。
2. `uv` 安装。
3. 依据 `pyproject.toml` 安装运行依赖。
4. Playwright Chromium 安装步骤。
5. Playwright 运行所需 Linux 系统库。
6. 默认工作目录和默认启动命令。

镜像目标是“开箱即可运行全部信息源”，因此知乎抓取依赖也要一并封装，而不是要求宿主机再单独执行浏览器安装。

### 4. Git 推送与认证

当前 README 已要求配置 `GITHUB_PAT`。容器化后继续沿用这一方式，但要让容器内 Git 推送完全非交互。

设计要求：

1. 不把 PAT 烧进镜像。
2. 不把 PAT 写入仓库跟踪文件。
3. 在容器运行时从 `.env` 读取 `GITHUB_PAT`。
4. `git push` 必须避免交互式用户名密码提示。

推荐做法：

- 在 `scripts/run.sh` 中为本次命令调用设置基于 `GITHUB_PAT` 的 HTTPS 认证方式。
- 认证只作用于当前运行过程，不污染用户全局 Git 配置。
- 若 `GITHUB_PAT` 缺失，脚本直接报错并退出。

这样既能保留现有“容器内完成发布”的工作流，也适合临时云服务器场景。

### 5. 权限与运行用户

Docker 不能自动消除所有权限问题，尤其当容器要写宿主挂载目录时。

本次设计要求：

1. 容器运行时对 `/app/output`、`/app/logs` 和 `.git` 所在工作树具备写权限。
2. 优先支持通过运行参数传入宿主 UID/GID，让生成文件与宿主用户保持一致。
3. 如果暂不做 UID/GID 映射，也要保证当前挂载目录对容器运行用户可写。

这部分是容器化后权限稳定性的关键。如果忽略 UID/GID 或挂载目录属主关系，权限错误会从“宿主脚本”转移成“容器写挂载失败”。

### 6. 容器启动流程

宿主机 cron 的职责从“直接执行脚本”改为“执行一次容器任务”。建议命令形态如下：

```bash
docker run --rm \
  --env-file /home/admin/octopus/.env \
  -v /home/admin/octopus:/app \
  -w /app \
  octopus:latest
```

如果需要控制挂载目录属主，还可以补充 `--user "$(id -u):$(id -g)"` 或等价配置。

容器内数据流为：

1. 启动容器
2. 执行 `scripts/run.sh`
3. 各抓取脚本生成缓存与数据库写入
4. `summarize.py` 生成日报
5. `git add output/daily/`
6. `git commit`
7. `git push`
8. 容器退出

### 7. 入口校验与错误处理

为了把故障从“玄学权限问题”变成“可定位错误”，入口需要明确校验：

1. `.env` 是否存在且可读。
2. `GITHUB_PAT` 是否存在。
3. 当前挂载目录是否包含 `.git`。
4. `output/` 和 `logs/` 是否可写。
5. 若启用知乎抓取，Playwright 和 Chromium 是否可用。

失败语义要求：

- 缺少挂载或权限不足时，输出中文清晰错误并以非零退出。
- `git commit` 没有变更时允许继续。
- `git push` 失败时必须显式报错，不能伪装成成功完成。
- 认证失败要让日志能区分是 PAT 问题，而不是一般权限问题。

### 8. 新增文件与文档

本次容器化设计预期新增：

1. `Dockerfile`
2. `.dockerignore`
3. README 中的 Docker 部署说明

如果为了简化 cron 命令，也可以新增一个轻量的宿主机包装脚本，例如 `scripts/run_docker.sh`，但这不是必须项。核心目标是避免把部署逻辑分散到多处。

## 测试计划

1. 构建 Docker 镜像并确保构建成功。
2. 继续运行仓库现有验证命令：
   - `uv run ruff check scripts/`
   - `uv run pytest test/`
   - `uv run pyright scripts test`
3. 在容器内执行一次主要路径，验证：
   - 能创建 `logs/`
   - 能写 `output/`
   - 能访问 `output/octopus.db`
   - 能运行 Playwright 依赖检查
4. 在缺少 `GITHUB_PAT`、缺少 `.git` 或挂载目录不可写时，确认错误提示清晰。

## 风险与缓解

- **风险：** 容器能运行，但写宿主挂载目录失败。  
  **缓解：** 优先支持以宿主 UID/GID 运行容器，并在入口显式检查目录可写性。

- **风险：** PAT 暴露到日志或命令历史。  
  **缓解：** 通过 `--env-file` 注入，不在脚本日志中输出 PAT 值，不把凭证写入仓库文件。

- **风险：** Playwright 镜像层较大，构建时间变长。  
  **缓解：** 接受镜像变大，换取部署一致性；优先稳定运行而非最小镜像体积。

- **风险：** Git 远程地址与 PAT 认证方式不兼容。  
  **缓解：** 在入口中统一处理 HTTPS 推送所需认证前提，并在失败时输出明确诊断。

## 实施轮廓

1. 新增 `Dockerfile` 和 `.dockerignore`。
2. 调整 `scripts/run.sh`，让容器环境下的 Git 推送支持 `GITHUB_PAT` 非交互认证。
3. 视需要增加启动前检查，明确报出挂载、权限和凭证问题。
4. 更新 README，补充 Docker 构建、运行和 cron 配置方式。
5. 验证镜像构建、测试命令和一次容器执行路径。
