# Bytesync API 常用命令大全

以下命令默认在服务器项目目录执行：

```bash
cd /home/yyy/bytesync-api
```

## Git 文件检查

```bash
# 查看当前分支、修改文件和暂存状态
git branch --show-current
git status --short

# 查看远程仓库地址
git remote -v

# 查看尚未放入暂存区的具体修改
git diff

# 查看已经 git add、等待提交的具体修改
git diff --staged

# 只看修改文件及行数统计
git diff --stat
git diff --staged --stat

# 检查多余空格、冲突标记等格式问题
git diff --check

# 查看最近提交
git log --oneline -10

# 查看本地尚未推送到 origin/main 的提交
git log --oneline origin/main..HEAD

# 比较当前分支和远程 main 的完整差异
git diff origin/main...HEAD
```

几个常见状态的区别：

- 工作区：已经修改，但还没有执行 `git add`。
- 暂存区：执行过 `git add`，将进入下一次提交。
- 本地提交：执行过 `git commit`，但可能还没有上传。
- 远程仓库：执行 `git push` 后，GitHub 才能看到提交。
- `git diff` 查看“工作区和暂存区”的区别。
- `git diff --staged` 查看“暂存区和上次提交”的区别。

## 安全提交并上传 GitHub

```bash
cd /home/yyy/bytesync-api

# 先同步远程提交信息，再检查当前状态
git fetch origin
git status --short
git branch --show-current
git remote -v

# 添加项目代码和文档；不要添加 .env.runtime
git add app/ docs/ tests/ requirements.txt requirements-test.txt Dockerfile

# 提交前再次检查内容
git diff --staged --stat
git diff --staged
git diff --staged --check

# 创建本地提交
git commit -m "Fix Gemini text meal analysis"

# 上传当前分支
git push -u origin "$(git branch --show-current)"
```

`.env.runtime` 包含密钥和密码，并且已被 Git 忽略。不要使用 `git add -f
.env.runtime`，也不要把密钥直接写进命令或文档。可用下面的命令确认它没有
进入暂存区：

```bash
git status --ignored --short .env.runtime
git diff --staged -- .env.runtime
```

## 查看容器服务

```bash
# 查看正在运行的容器
docker ps

# 同时查看已停止的容器
docker ps -a

# 查看 API 容器状态
docker ps --filter name=bytesync-api

# 查看最近 160 行日志
docker logs --tail 160 bytesync-api

# 持续查看新日志，按 Ctrl+C 退出
docker logs -f --tail 100 bytesync-api

# 检查 API 和数据库是否健康
curl --fail-with-body http://127.0.0.1:8000/health
```

## 启动、停止和重启现有容器

```bash
# 停止 API
docker stop bytesync-api

# 再次启动已经停止的 API
docker start bytesync-api

# 直接重启 API
docker restart bytesync-api

# 启动后检查状态和日志
docker ps --filter name=bytesync-api
docker logs --tail 160 bytesync-api
curl --fail-with-body http://127.0.0.1:8000/health
```

`docker restart` 只重新启动原容器，不会加载新镜像，也不会重新读取
`--env-file`。代码或 `.env.runtime` 变化后应重新创建容器。

## 构建并替换 API 容器

先构建镜像，构建成功后再停止当前服务：

```bash
cd /home/yyy/bytesync-api
docker build -t backend-api:latest .
```

给旧容器使用一个尚未存在的备份名，例如
`bytesync-api-before-update-20260913`：

```bash
docker stop bytesync-api
docker rename bytesync-api bytesync-api-before-update-20260913

docker run -d \
  --name bytesync-api \
  --restart unless-stopped \
  --network bytesync-db_default \
  --env-file /home/yyy/bytesync-api/.env.runtime \
  -p 8000:8000 \
  backend-api:latest

docker ps --filter name=bytesync-api
docker logs --tail 160 bytesync-api
curl --fail-with-body http://127.0.0.1:8000/health
```

容器名称必须唯一。如果示例备份名已存在，应换一个新名称，可先检查：

```bash
docker ps -a --format '{{.Names}}'
```

## 部署失败时回滚

下面命令中的备份名必须和替换时使用的名称一致：

```bash
docker stop bytesync-api
docker rename bytesync-api bytesync-api-failed-20260913
docker rename bytesync-api-before-update-20260913 bytesync-api
docker start bytesync-api

docker ps --filter name=bytesync-api
docker logs --tail 160 bytesync-api
curl --fail-with-body http://127.0.0.1:8000/health
```

## 自动化测试

测试使用隔离的 PostgreSQL 容器，不应连接生产数据库：

```bash
cd /home/yyy/bytesync-api
docker build -f tests/Dockerfile -t bytesync-ai-tests .

docker run -d --rm \
  --name bytesync-meals-test-db \
  --network none \
  -e POSTGRES_HOST_AUTH_METHOD=trust \
  postgres:17

docker exec bytesync-meals-test-db pg_isready -U postgres

docker run --rm \
  --network container:bytesync-meals-test-db \
  -v /home/yyy/bytesync-api:/workspace:ro \
  -e PYTHONDONTWRITEBYTECODE=1 \
  bytesync-ai-tests

docker stop bytesync-meals-test-db
```
