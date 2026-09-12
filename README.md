# WorkBuddy 国际版多账号反代网关

本项目为 **WorkBuddy 国际版多账号反代网关**，将腾讯 **www.workbuddy.ai** 原生服务封装为标准 OpenAI 兼容接口，支持多账号负载轮询、OAuth 一键免客户端登录、Web 监控看板、实时积分查询、以及 Chat Completions 与 Responses API (Codex / Claude Code) 双协议全功能支持。

- **开箱即用**：包内自带 Python 运行时，不用装任何东西
- **多账号池**：轮询使用，某个账号被上游拒绝时自动切换
- **两种登录方式**：浏览器 OAuth 自主登录 / 导入已登录的桌面应用凭证
- **用量与性能统计**：内置看板，按账号、按模型拆分

> **凭证是明文保存的。** 账号文件在 accounts/ 目录下，和桌面应用的做法一致。
> 不要把该目录放到共享盘或同步盘里。

---

## 一、启动

解压后双击 **start-wb-proxy.bat**。看到这些就是好了：

    WorkBuddy 反代
    接口地址 : http://127.0.0.1:8788/v1
    用量看板 : http://127.0.0.1:8788/

**窗口不要关**，关掉窗口 = 停止服务。

### 第一次运行（还没有账号）

程序会先尝试**自动导入桌面应用已登录的国际版账号**（如果那台机器装过）。

没找到也没关系 —— **服务照样启动**。这时候打开看板：

    http://127.0.0.1:8788/

「账号」区域会显示一个大按钮「**登录新账号**」。
点它，浏览器登录完成后账号自动加入，立刻就能用。

不需要命令行操作，也不需要提前装任何东西。

### 环境要求

| 项目 | 要求 |
|---|---|
| Python | **已内置**，无需安装 |
| 第三方库 | 无 |
| 桌面应用 | **可选**，只在用「导入桌面凭证」时才需要 |

包里带了一个精简的 Python 3.12 运行时（python/ 目录，约 30 MB）。
双击 bat 就能跑，不用在系统里装 Python。

启动器按顺序找解释器，每个都实跑验证（坏的会自动跳过）：

1. 本目录下的 python\python.exe ← **包内自带的这个**
2. 系统 PATH 里的 python
3. py 启动器
4. Codex 自带运行时里的 Python

想换成自己的 Python，把 python 目录删掉即可，启动器会自动往后找。

### 让局域网其它设备使用

默认只监听 127.0.0.1，**只有本机能访问**。要让手机、平板、别的电脑也能用：

**双击 `start-wb-proxy-lan.bat`**（不是普通的那个）。它会打印出你需要的一切：

    ==============================================================
    LAN MODE - reachable from other devices

      API       : http://192.168.1.50:8788/v1
      Dashboard : http://192.168.1.50:8788/

      API Key   : qwer.1234

      Open the dashboard (key already included):
        http://192.168.1.50:8788/?key=qwer.1234

      Clients: Base URL = the API address above, then paste the key.
    ==============================================================

**在别的设备上怎么填：**

| 项目 | 值 |
|---|---|
| Base URL | 上面打印的 **API** 地址（例如 http://192.168.1.50:8788/v1） |
| API Key | 上面打印的那串密钥 |

看板直接点上面的 "Open the dashboard" 链接就能进（密钥已带在 URL 里）。

**关于密钥**

局域网模式下默认固定密钥为：**`qwer.1234`**。

客户端配置时将 API Key 填为 `qwer.1234` 即可。

如果想自定义改成别的密钥，可以在启动命令后带参数或设置环境变量：

    start-wb-proxy-lan.bat 8788 my-custom-key
    或者
    set WB_PROXY_KEY=my-custom-key
    start-wb-proxy-lan.bat

**连不上怎么办**

Windows 防火墙默认会拦截。首次运行时会弹出"是否允许访问"，**选允许**。

如果弹窗已经错过了，或者没弹：右键 **`allow-firewall.bat`** → 以管理员身份运行，
它会加一条放行规则（会弹 UAC 确认）。

要撤销这条规则：

    netsh advfirewall firewall delete rule name="WorkBuddy proxy (TCP 8788)"

**安全提醒**

- 密钥等于你的账号使用权，别发到公开群里
- 只在你信任的网络里开（家里的网、自己的热点）。公共 WiFi 上别开
- 用完把窗口关了，服务就停了
- 不想暴露时，就用普通的 `start-wb-proxy.bat`（只听本机）

---

## 二、添加账号

打开看板 http://127.0.0.1:8788/ ，在「**账号**」区域操作。

### 方式一：浏览器登录（推荐，不依赖桌面应用）

1. 点「**登录新账号**」
2. 弹出的窗口里会显示一个 workbuddy.ai/login?... 链接，点开
3. 在浏览器里完成登录
4. 回到看板 —— 程序每 2.5 秒自动检测，成功后账号自动加入池子

整个流程不需要手动复制粘贴任何东西。

### 方式二：从桌面应用导入

已经装了 WorkBuddy AI 并登录过的，点「**从桌面应用导入**」，一键把它存的凭证拉进来。

国内版凭证（copilot.tencent.com）会被自动跳过，只认国际版。

### 多账号怎么工作

- 请求在可用账号之间**轮询**（round-robin）
- 某个账号返回 401/403/429 时，自动换下一个重试，并让该账号短暂冷却
- 每个账号可单独**启用 / 停用 / 刷新 / 删除**
- 看板按账号显示各自的请求数和 token 消耗

账号之间互不影响：A 账号额度用完了，B 账号接着跑。

---

## 三、客户端配置

| 项目 | 值 |
|---|---|
| Base URL | http://127.0.0.1:8788/v1 |
| API Key | 局域网模式默认为 qwer.1234（本机模式可填可不填） |
| 模式 | **Chat Completions** 和 **Responses API** 都支持 |
| 模型 | 点「获取模型」自动列出，也可手填 |

可用模型（21 个，含完整能力元数据）：

    deepseek-v4.1-flash   gpt-6-astra      gpt-5.6-sol     gpt-5.6-terra
    gpt-5.6-luna          gpt-5.5          gpt-5.4         gpt-5.3-codex
    gemini-3.5-flash      glm-5.3          glm-5.2         kimi-k3
    kimi-k2.6             hy4-preview      hy4-preview-f   hy3
    default-model         fast-model       balanced-model  primary-model
    deep-model

**这份列表已内置在程序里**，所以即使那台机器没装 WorkBuddy 桌面应用
（也就没有本地模型缓存），列表依然是完整的 21 个 —— 包括
`deepseek-v4.1-flash` 和 `gpt-6-astra` 这两个上游 CLI 接口不肯吐出来的。

如果桌面应用或接口返回了更新的列表，会**自动覆盖**内置的那份
（新模型会出现，改动的元数据会更新）；内置目录只是兜底。

---

## 四、看板

http://127.0.0.1:8788/

| 区域 | 内容 |
|---|---|
| **账号** | 登录 / 导入 / 刷新 / 启停 / 删除；每账号的请求数与 token |
| **汇总卡片** | 请求数、总 token、输入/输出、思考 token、缓存命中、失败数 |
| **性能指标** | 首字延迟、生成耗时、端到端延迟、生成速度、缓存命中率（平均/P50/P90/P99） |
| **按模型** | 各模型用量与占比 |
| **最近请求** | 逐条明细，含所属账号、缓存命中率、失败标记 |

---

## 五、接口一览

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | / | 用量看板 |
| POST | /v1/chat/completions | 对话（Chat Completions 格式） |
| POST | /v1/responses | 对话（Responses API 格式） |
| GET | /v1/models | 模型列表（含能力元数据） |
| GET | /health | 状态摘要 |
| GET | /accounts | 账号列表 |
| POST | /accounts/login/start | 发起 OAuth 登录 |
| GET | /accounts/login/poll?state=X | 轮询登录结果 |
| POST | /accounts/login/cancel | 取消登录 |
| POST | /accounts/import/desktop | 导入桌面应用凭证 |
| POST | /accounts/refresh | 刷新令牌（带 uid 刷一个，不带刷全部） |
| POST | /accounts/set | 启用/停用单个账号 |
| POST | /accounts/set-all | 全部启用/停用 |
| POST | /accounts/delete | 删除账号 |
| GET | /usage | 累计用量 |
| GET | /usage/recent?limit=N | 最近 N 条明细 |
| GET | /usage/perf | 性能分位数 |
| GET | /usage/by-account | 按账号聚合 |

两种对话接口都支持 stream: true/false。

---

## 六、启动参数

| 参数 | 默认 | 说明 |
|---|---|---|
| --port | 8788 | 监听端口 |
| --host | 127.0.0.1 | 监听地址。改成 0.0.0.0 才能被局域网访问，**务必同时加 --api-key** |
| --api-key | 无 | 要求 Bearer 令牌（也可用 WB_PROXY_KEY） |
| --accounts-dir | ./accounts | 账号文件目录 |
| --usage-dir | ./usage | 用量日志目录 |
| --system-prompt | You are a helpful assistant. | 请求里没有 system 时自动补的一条 |
| --user-agent | 自动镜像官方客户端 | 覆盖发给上游的 User-Agent |
| --info | 自动查找 | 从指定凭证文件导入一个账号 |
| --import-desktop | 关 | 导入桌面凭证后列出账号并退出 |

---

## 七、数据文件

| 路径 | 内容 |
|---|---|
| python/ | 内置 Python 运行时（可删） |
| accounts/<uid>.json | 每个账号一份，**明文**存 token |
| usage/usage.jsonl | 逐条请求记录，追加写入，重启不丢 |
| usage/usage-summary.json | 累计汇总快照 |

usage.jsonl 每条包含：时间、模型、**所属账号**、流式/非流式、耗时、首字延迟、
输入/输出/思考/缓存 token、生成速度、缓存命中率、前缀指纹。

---

## 八、原理

| 项目 | 值 |
|---|---|
| 登录发起 | POST /v2/plugin/auth/state?platform=CLI |
| 登录轮询 | GET /v2/plugin/auth/token?state=X |
| 账号信息 | GET /v2/plugin/login/account?state=X |
| 令牌刷新 | POST /v2/plugin/auth/token/refresh |
| 对话 | POST /v2/chat/completions |
| 模型 | GET /v2/enterprises/personal/models |
| 桌面凭证 | %LOCALAPPDATA%\CodeBuddyExtension\Data\Public\auth\workbuddy-desktop-ai.info |
| 模型目录 | ~/.workbuddy-ai/cache/acc-product-config-v3.json |

**客户端标识（User-Agent）。**

程序发出的 UA 是**照官方国际版客户端的行为复刻的**，不是随便编的：

    WorkBuddy/5.5.2 WorkBuddy AI/5.5.2 CLI/5.5.2

这个格式来自客户端自身的代码：

| 来源 | 值 |
|---|---|
| 品牌常量 WORKBUDDY_PLATFORM | WorkBuddy |
| product.json productName | WorkBuddy AI |
| 版本（自动探测） | 5.5.2 |
| CLI 扩展 | CLI/5.5.2 |

版本号会在启动时从本机客户端探测（last-launch.json / 产品配置缓存），
没装客户端的机器用内置默认值。想手动指定就用 --user-agent。

（注：早期版本曾用国内版的 CLI 标识，品牌和版本号都对不上国际站，已修正。）

**只认国际版。** 登录时校验 JWT 的 issuer；导入的凭证如果是国内版
（copilot.tencent.com）会被拒绝。

**上游的两个硬性约束（已处理）**

1. **纯流式**：stream:false 会被拒（code 11101）。程序永远用流式打上游，
   客户端要非流式时在本地折叠。
2. **首条必须是 system**：否则报 code 11128。请求里没有 system 时自动补一条。

**提示词不会被污染。** 发给上游的内容 = 客户端发的原样 + 一条可自定义的 system
（仅当客户端没带时）。WorkBuddy 自己的 agent 提示词不会混入。

**思考等级。** 请求里加 reasoning_effort（low / medium / high / xhigh / max）。
不是每个模型都能调：deepseek-v4.1-flash 固定 high 且常开，
gpt-6-astra 支持五档并可关闭。GET /v1/models 会说明各自情况。

**缓存。** 上游按 128 token 一块做前缀缓存，前缀必须完全相同才命中。
短请求命不中是正常的；多轮对话、稳定长 system 的场景可达 90%+。

---

## 九、注意事项

- 默认只绑 127.0.0.1，局域网访问不到。
- **凭证明文保存**，注意 accounts/ 目录的访问权限。
- 令牌过期会自动刷新；刷新失败说明要在浏览器里重新登录该账号。
- 模型列表来自桌面应用缓存，应用启动时才刷新。想拿最新列表就开一下应用再重启本程序。
- 走的是你账号的额度，别拿去做批量并发。

---

## 十、常见问题

**双击 bat 后窗口一闪就没了**
打开命令行，cd 到本目录，执行 start-wb-proxy.bat 看报错。

**提示 "[ERROR] No usable Python found"**
包内自带的 python 目录被删了或损坏。重新解压一次压缩包；
或者装一个 Python 3.9+ 并把 python 目录删掉，启动器会改用系统的。

**提示"[已有一个反代在 8788 端口运行]"**
已经启动过了。要重启就先关掉原来那个窗口。

**启动后提示"NO ACCOUNTS YET"**
正常 —— 这台机器还没有账号。打开看板点「登录新账号」，
浏览器登录完成后账号会自动加入，无需重启程序。

**请求返回 503 no usable account**
所有账号都被停用、冷却中或已过期。到看板「账号」区域检查，必要时重新登录。

**报 11102 model service info not found**
模型名没被上游注册。换成 /v1/models 里列出的模型。

**报 11134 the model provider is temporarily unavailable**
上游临时不可用（gpt-5.6-luna 比较容易遇到），重试即可。

**缓存命中率一直是 0**
正常现象 —— 缓存粒度是 128 token，太短的请求命不中。

---

## 十一、致谢与引用声明 (Credits & References)

本项目在协议兼容、风控规避与链路优化过程中，深度参考并吸纳了开源社区现有项目的经验与逆向成果，特此致谢：

- **[Sliverkiss/workbuddy2api](https://github.com/Sliverkiss/workbuddy2api)**：
  - **指纹脱敏管线设计**：吸纳了其出站请求体脱敏策略，彻底解决 Codex CLI / Claude Code 默认系统指令触发上游 WAF `code 11128 Illegal API invocation` 拦截的问题。
  - **DeepSeek 多轮思维链回填**：参考了其关于 `requiresReasoningContentOnAssistantMessages` 的逆向结论，实现了多轮对话历史中自动回填 `reasoning_content`，保证思维链上下文不丢失。
  - **`tool_choice` 归一化**：吸纳了其将复杂对象安全降级为上游 Go 后端原生标量字符串的处理逻辑，规避 `11101` 语法报错。
  - **实时积分接口**：参考了其通过 `POST /v2/billing/meter/get-user-resource` 查询与聚合账户资源包用量的协议实现。
- **[lovingfish/workbuddy-cliproxy](https://github.com/lovingfish/workbuddy-cliproxy)** 与 **[mmqz/cpa-multi-plugins](https://github.com/mmqz/cpa-multi-plugins)**：
  - 提供了早期关于 WorkBuddy 网关通信与 OAuth 授权流程的原型参考。

---

## 十二、免责声明 (Disclaimer)

1. 本项目为非官方自托管网关，仅供技术研究、逆向协议学习与个人合法授权账号在私有环境测试使用。
2. 本项目不提供任何账号及额度。请严格遵守相关服务条款，禁止用于任何商业转售、恶意并发或批量违规操作。
