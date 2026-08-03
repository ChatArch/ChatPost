# CLI 结构设计

!!! warning "状态：设计提案，不是当前可用命令"
    `ChatPost 0.0.2` 当前只实现 `chatpost --help` 和 `chatpost --version`。本页定义首个功能版本的预期命令边界，用于实现前 Review；示例现在不能直接执行。

Browser Runner、Chrome 与多账号隔离见 [Browser Runner 与账号隔离](browser-runners.md)。

## 设计目标

ChatPost CLI 同时服务两类用户：

- 人在终端中准备内容、登录账号、打开草稿并 Review；
- 自动任务以 JSON 输出调用同一控制面，但默认只到草稿，不替人绕过登录或点击最终发布。

首版遵循以下原则：

1. **显式目标**：目标写成 `platform@account`，例如 `zhihu@personal`。
2. **创建与更新分离**：`draft create` 和 `draft update` 不互相回退。
3. **Runner 与账号分离**：账号是逻辑发布目标，Runner 是持有浏览器登录态的执行环境。
4. **默认 fail-closed**：账号、文章 ID、Runner 或登录状态不明确时停止，不猜测、不自动新建副本。
5. **最终发布是人工 checkpoint**：首版没有自动 `publish` 命令。

## 当前真实命令

```text
chatpost
├── --help                     # 查看当前真实命令树
└── --version                  # 输出安装版本
```

## 首版预期命令树

以下全部为提案：

```text
chatpost
├── init [PATH]                # 初始化 workspace、配置和 publication ledger
├── platform
│   ├── list                   # 列出已安装 adapter
│   └── show PLATFORM          # 查看平台能力：draft/update/images/review 等
├── runner
│   ├── add NAME               # 注册 host 或 docker Browser Runner
│   ├── list                   # 列出 Runner 与健康状态
│   ├── show NAME              # 查看 runtime、profile ref、端口和绑定账号
│   ├── start NAME             # 启动 ChatPost 拥有的 Runner
│   ├── stop NAME              # 优雅停止 ChatPost 拥有的 Runner
│   ├── status NAME            # 检查进程、CDP、bridge 和扩展连接
│   ├── doctor NAME            # 检查二进制、目录权限、端口冲突和版本
│   └── open NAME              # 打开可见浏览器，供登录或人工接管
├── account
│   ├── add TARGET             # 注册 platform@alias，并绑定 Runner
│   ├── list                   # 列出逻辑账号，不显示 Cookie
│   ├── show TARGET            # 查看绑定关系和最近 auth 状态
│   ├── login TARGET           # 打开登录页并进入人工 checkpoint
│   └── status TARGET          # 只读检查平台登录态
├── plan SOURCE                # 解析内容并生成无远端写入的执行计划
├── draft
│   ├── create SOURCE          # 显式创建草稿；成功后写入 ledger
│   └── update SOURCE          # 只更新已有 ID；缺 ID 时失败
├── publication
│   ├── list                   # 按 source/target/status 查询发布记录
│   ├── show REF               # 查看 ID、hash、receipt 和状态
│   ├── status REF             # 只读回查平台状态
│   ├── open REF               # 在正确 Runner 中打开草稿供 Review
│   └── reconcile REF          # 人工处理 RESULT_UNKNOWN，不自动重试
├── config
│   ├── path                   # 显示生效配置和 ledger 路径
│   ├── show                   # 显示脱敏后的合并配置
│   └── validate               # 校验 schema、引用和端口分配
└── doctor                     # 全局检查配置、Runner、adapter 和 ledger
```

## 目标语法

统一使用：

```text
<platform>@<account-alias>
```

示例：

```text
zhihu@personal
zhihu@brand
csdn@personal
xiaohongshu@brand
```

`account-alias` 是本地逻辑名称，不是平台用户名，也不应包含手机号、邮箱或其他隐私信息。

## 推荐工作流

以下展示预期交互，不代表当前已经实现：

```bash
# 1. 初始化控制面
chatpost init

# 2. 注册一个直接运行宿主机 Chrome 的 Browser Runner
chatpost runner add mac-personal --runtime host --browser auto
chatpost runner doctor mac-personal
chatpost runner start mac-personal --visible

# 3. 注册逻辑账号；不把密码或 Cookie 交给 CLI
chatpost account add zhihu@personal --runner mac-personal
chatpost account login zhihu@personal
chatpost account status zhihu@personal

# 4. 纯本地计划
chatpost plan article.md --to zhihu@personal --output json

# 5. 显式创建草稿
chatpost draft create article.md --to zhihu@personal

# 6. 打开草稿，让人 Review 和最终发布
chatpost publication open article-slug@zhihu@personal
```

## Runner 命令边界

`runner add` 预期支持：

```text
--runtime host|docker
--browser auto|chrome|chromium|chrome-for-testing
--binary PATH               # host runtime 可选
--user-data-dir PATH        # 默认由 ChatPost 创建专属目录
--visible / --headless
```

安全默认值：

- `host` 是默认 runtime；Docker 不是要求。
- CDP 与 bridge 只绑定 `127.0.0.1`。
- 每个 Runner 使用独立 user-data-dir、debug port、bridge port 和 token。
- bridge token 使用 secret reference，不出现在 `config show`、ledger 或日志中。
- `runner stop` 只优雅停止由 ChatPost 启动且身份匹配的进程。

## Account 命令边界

`account add` 只注册映射：

```text
logical target -> runner -> browser persona -> platform session
```

它不会：

- 接收平台密码；
- 导入 Cookie；
- 绕过验证码或二维码；
- 自动声明账号已经登录。

`account login` 的职责是打开正确 Runner 和平台登录页，随后等待用户在浏览器中完成操作。`account status` 再通过 adapter 做只读验证。

## Plan 与远端写入

`plan` 必须保持纯读：

- 解析 Markdown、front matter 和本地图片；
- 解析目标账号及 Runner；
- 读取 ledger，判断目标是否已有 draft/article ID；
- 输出 adapter 能力和预计操作；
- 不启动草稿创建、图片上传或平台更新。

机器调用可使用：

```bash
chatpost plan article.md --to zhihu@personal --output json --no-interactive
```

## Create 与 Update 必须 fail-closed

```text
draft create
  -> 只允许 create
  -> 如果 ledger 已有 active draft，可要求显式确认或改用 update

draft update
  -> 只允许 update
  -> 必须从 ledger 或 --post-id 得到已有 ID
  -> adapter/RPC/ID 缺失时失败
  -> 绝不回退成 create
```

这条边界用于避免自动任务因字段丢失、扩展版本不匹配或断线而制造重复草稿。

## Publication ledger

首版 ledger 至少记录：

```text
source_ref
source_sha256
target                 # platform@alias
runner
mode                   # create_draft / update_draft
draft_id / article_id
public_url / review_url
last_success_commit
status
created_at / updated_at
```

ledger 不记录：

- Cookie、Local Storage；
- 平台密码、短信验证码；
- bridge token 明文；
- Chrome profile 文件内容。

## 状态与恢复

建议统一状态：

```text
PLANNED
RUNNER_UNAVAILABLE
NEEDS_LOGIN
READY
RUNNING
DRAFT_CREATED
AWAITING_REVIEW
COMPLETED
FAILED
RESULT_UNKNOWN
NEEDS_ACTION
```

如果请求已发出但回执丢失，必须写入 `RESULT_UNKNOWN`。用户先运行 `publication status` 或 `publication reconcile` 回查，不允许自动重试 create/update。

## 首版不提供自动 Publish

`draft create/update` 到草稿即结束。用户通过 `publication open` 在平台页面 Review 并最终发布。

未来如果增加 `publish`，必须作为独立 capability 设计，至少要求：

- 平台与账号明确授权；
- 可审计的显式确认；
- 与 draft/update 分开的测试和权限；
- 不绕过验证码、风控和平台规则。

## 实现顺序

建议正式开发按以下顺序：

1. `init`、config schema 与 ledger；
2. `runner add/list/status/doctor` 的 host runtime；
3. `account add/status/login checkpoint`；
4. `platform list/show` 与 adapter protocol；
5. `plan`；
6. `draft create`；
7. `draft update` 与 fail-closed contract；
8. `publication open/status/reconcile`；
9. Docker runtime；
10. 远端 Runner 与更多平台 adapter。

每个命令只有在代码、测试和帮助文本都存在后，才能从“提案”改成“已实现”。
