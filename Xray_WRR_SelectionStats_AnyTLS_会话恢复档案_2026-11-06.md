# Xray + AnyTLS + WRR + Selection Stats 项目会话恢复档案

> **用途**：在新的 ChatGPT 会话中，上传本 Markdown，供接手模型快速恢复本次完整项目背景、已经验证的结果、关键源码与 CI 版本、兼容性测试、踩坑与下一步工作。  
> **归档日期**：2026-11-06（本次对话主要发生于 2026-11-05）  
> **状态**：三功能组合版已完成 **Linux AMD64 本机端到端验证**；旧 WRB Manager 的 WRR 生成语法已验证兼容；公网/长期稳定性及自动健康恢复仍待验证。  
> **重要**：此文档记录对话内证据与报告，不代表对 GitHub 仓库**此刻**分支状态的实时同步检查。

---

## 0. 给接手模型的「一分钟上下文」

用户管理 GitHub 仓库 **[WXMa1/myxray](https://github.com/WXMa1/myxray)**，其 Xray 定制版原本通过 GitHub Actions 在 **XTLS/Xray-core** 上注入 **Weighted Round Robin（WRR）** 以及原生 **Selection Stats（按节点统计被 WRR 选择次数）**。用户希望在**不破坏原有 WRR/Stats** 的前提下添加 **AnyTLS**，先单独构建，再做完整三功能组合构建，并确保旧版 **WRB 10.1.4 管理器**生成的 WRR 配置仍可使用。

**已得到可验证的组合基线**：

| 项目 | 当前基线 |
|---|---|
| 官方 Xray 源码 | `XTLS/Xray-core`，commit `a52db8f6ed19384dbc91a6f7e2cf4c09fbe7c2ca` |
| AnyTLS 移植来源 | `ynetlab/Xray-core`，commit `0721f9b543a6c20f503c1ac181eeb27d98d808f2` |
| WRR + Stats 补丁来源 | `WXMa1/myxray`，commit `8fe9f7f757de245e2b6a1be875da4747f7aaf9e0` |
| Xray 版本 | `26.10.31 Custom`，Go `1.27.3` |
| 已实测二进制 | `xray-wrr-anytls-linux-amd64` |
| 二进制 SHA256 | `6f98cbc113eb6a3b08dedeaa65a1c96d236dedde578e076e9c5025565f2fcb3c` |
| 当前组合工作流路径 | `.github/workflows/build-wrr-selection-stats-anytls.yml` |
| 当前工作流逻辑版本 | **V5**：解决 WRR 脚本的工作目录问题及 Linux AMD64 路由测试缺 `geosite.dat` 问题 |

**实测**：AnyTLS+TLS、AnyTLS+REALITY、本地 SOCKS5→AnyTLS→HTTP 回环；WRR 两节点 3:1；Xray Stats API；两个 AnyTLS 候选出站同时参与 WRR；旧版 WRB 生成的正则匹配权重格式。TLS 和 REALITY 联合测试分别 12/12 HTTP 200，分配各为 9:3，Stats API 各为 9:3。证据见 §6/§8。

**下一个推荐验证目标**：`autoHealthWRR` 的节点故障摘除/恢复、`autoWeightWRR` 动态权重调整、WRB Manager 在实际 iKuai 部署环境中加载新内核的完整兼容性。**不要将「配置可解析」误称为「故障恢复已经通过实测」。**

**对话偏好**：用户多次强调 GitHub Action 要**完整显示在网页上，方便直接全选复制**，而不仅是下载文件或提供一个需要手工拼接的片段。因此后续若修复工作流，优先给出完整 YAML，清楚写路径、版本、变动。

---

## 1. 术语与项目关系（务必分清）

- **Xray-core**：官方 Go 代理核心。用户的 Action 下载官方源码后注入定制代码并交叉编译。
- **WRR**：Weighted Round Robin，加权轮询策略，配置类型名固定为 `weightedRoundRobin`。
- **Selection Stats**：WRR 选中每个候选节点时累加原生 Xray 统计量，命名结构 `outbound>>>节点Tag>>>wrr>>>selections`，可用 StatsService 查询。
- **AnyTLS**：单独代理协议，可作为 Xray 入站/出站。它与 REALITY 并不互斥。
- **REALITY**：Xray TLS 安全层/握手伪装机制，可和 AnyTLS 组合。本次测试过 AnyTLS+REALITY。
- **WRB 10.1.4**：用户上传的另一套管理器/发布包，能够**动态生成** Xray 的 WRR Runtime 配置。注意“WRB”是管理系统名，“WRR”才是加权轮询算法；不要混用这两个名词。
- **`autoHealthWRR` / `autoWeightWRR`**：旧 WRB Manager 的可选健康检测和自动权重功能；不是简单 `weightedRoundRobin` 配置本身就能证明其全部行为。

### 重要仓库及上游参考

- 用户项目：[https://github.com/WXMa1/myxray](https://github.com/WXMa1/myxray)
- 官方：[https://github.com/XTLS/Xray-core](https://github.com/XTLS/Xray-core)
- AnyTLS 原始 PR（未合并）：[https://github.com/XTLS/Xray-core/pull/5907](https://github.com/XTLS/Xray-core/pull/5907)，标题 `Proxy: Add AnyTLS protocol`，作者 `wyx2685`。
- 实际引用的第三方移植：[https://github.com/ynetlab/Xray-core/commit/0721f9b543a6c20f503c1ac181eeb27d98d808f2](https://github.com/ynetlab/Xray-core/commit/0721f9b543a6c20f503c1ac181eeb27d98d808f2)
- 上游 GeoData：[https://github.com/XTLS/Xray-rules-dat](https://github.com/XTLS/Xray-rules-dat)
- 用户实际提供的 ARM64 Actions Artifact：[https://github.com/WXMa1/myxray/actions/runs/42035445692/artifacts/13417388353](https://github.com/WXMa1/myxray/actions/runs/42035445692/artifacts/13417388353)（当时 GitHub 报告上传大小 11,193,060 字节；Artifact 访问可能需要登录权限）
- 早期 invalid workflow 运行：[https://github.com/WXMa1/myxray/actions/runs/41968035776/workflow](https://github.com/WXMa1/myxray/actions/runs/41968035776/workflow)

### 争端背景（仅作起点）

会话一开始讨论过 AnyTLS 与 REALITY/Xray 生态的争议。技术上它们**并非必须二选一**：AnyTLS 是代理协议，REALITY 是安全层。Xray 官方维护者没有合并 AnyTLS PR，但因项目开源，第三方可以 Fork/移植。用户据此决定在自己的 `myxray` Actions 中添加 AnyTLS。**恢复本项目开发无需重新纠缠社区争端。**

---

## 2. 用户起始诉求与最终完成范围

1. 起初用户的 `myxray` Action 只为官方 Xray 添加 **WRR + Selection Stats**。
2. 要求**先实现独立 AnyTLS Action**，暂不合并 WRR。独立版已构建并完成 AnyTLS+TLS、AnyTLS+REALITY 本机回环验证。
3. 再要求做**第三个组合 Action**，同时包含 WRR + Selection Stats + AnyTLS，保留旧两个独立工作流。
4. 组合 Action 多次遇到 CI 问题，逐项修复后五个平台的构建矩阵启动并产出 Artifact。特别是 Linux AMD64 先执行路由测试，因缺 GeoData 报错，V5 修复后用户上传了其 AMD64 组合 Artifact 进行实测。
5. 用户又提供 `WRB 10.1.4` 大型旧版发布包，要求核对新组合内核是否仍兼容**旧 Manager 实际生成的 WRR JSON**。已确认核心字段/正则匹配兼容、实测与 AnyTLS 联合工作；Manager 生产环境完整兼容性仍未测。
6. 本文档是为了**未来恢复会话**，不是要求重新编写核心或修改现有仓库。

---

## 3. 三套 GitHub Actions 的区别

| 工作流 | 功能 | 备注 |
|---|---|---|
| `.github/workflows/build-weighted-xray-with-stats.yml` | 原始 WRR + Selection Stats | 用户仓库已有；依赖 `scripts/patch_weighted_balancer_with_stats.py`，运行时必须在 Xray-core 源码根目录 |
| `.github/workflows/build-anytls-xray.yml` | 单独 AnyTLS | 由本次会话新增，固定引用 ynetlab commit；独立版已经进行本机 AnyTLS/REALITY 测试 |
| `.github/workflows/build-wrr-selection-stats-anytls.yml` | **三功能组合** | 本次开发重点；V5 合并改动、跨平台编译、Linux AMD64 GeoData + 路由测试 |

工作流**不应**在构建时复用/覆盖原始 WRR 或 AnyTLS 的二进制文件。正确方式是：官方 Xray 源码 → 打 WRR/Stats 源码补丁 → 打 AnyTLS 源码补丁 → **同一个 Go 项目**编译一个组合核心。

### 3.1 组合版构建矩阵

- `linux/amd64` → `xray-wrr-anytls-linux-amd64`
- `linux/arm64` → `xray-wrr-anytls-linux-arm64`
- `windows/amd64` → `xray-wrr-anytls-windows-amd64.exe`
- `darwin/amd64` → `xray-wrr-anytls-darwin-amd64`
- `darwin/arm64` → `xray-wrr-anytls-darwin-arm64`

均通过 `actions/upload-artifact` 上传对应二进制、`.sha256`、`build-info-...txt` 和 `wrr-validation.txt`；保留期在 V5 中为 14 天。其他架构**编译成功 ≠ 已做对应硬件运行测试**。

### 3.2 WRR/Stats 补丁实际改动

经解包成功的 **Linux AMD64 组合 Artifact**，`wrr-validation.txt` 记录 WRR 补丁修改了：

```text
app/router/config.go
app/router/strategy_weightedroundrobin.go
app/router/strategy_weightedroundrobin_test.go
infra/conf/router.go
infra/conf/router_strategy.go
```

WRR 补丁脚本实际路径：

```text
$GITHUB_WORKSPACE/patch-repo/scripts/patch_weighted_balancer_with_stats.py
```

**重大易错点**：必须进入 `$GITHUB_WORKSPACE/xray-core` **再运行这个脚本**；它通过当前工作目录中的 `go.mod` 判断自己正位于 Xray-core 项目根目录。

### 3.3 AnyTLS 的注入位置（核心技术实现）

- checkout `ynetlab/Xray-core` 固定 Commit `0721f9b...` 到 `anytls-source/`。
- 仅将 `anytls-source/proxy/anytls` 目录复制到 `xray-core/proxy/anytls`。
- 复制 `anytls-source/infra/conf/anytls.go` 到 `xray-core/infra/conf/anytls.go`。
- 在 `xray-core/infra/conf/xray.go` 的 **inboundConfigLoader** 和 **outboundConfigLoader** 中注册 `"anytls"` 对应的 `AnyTLSServerConfig`/`AnyTLSClientConfig`。
- 在 `xray-core/main/distro/all/all.go` 中匿名导入 `github.com/xtls/xray-core/proxy/anytls`。
- `gofmt` 后构建；不要直接用第三方 Fork 整个核心替换官方源码，也不要遗漏原 WRR 改动。
- 这套补丁含固定源码定位锚点，随着 Xray `main` 演进，未来可能失效，届时应核对 `infra/conf/xray.go`、`main/distro/all/all.go` 的实际结构。

---

## 4. CI 报错时间线、根因与已确认的修复

| 阶段 | 用户反馈/关键报错 | 根因 | 采取的修复 |
|---|---|---|---|
| 初版组合 Action | `Invalid workflow file`、`Line: 92, Col: 14`、`An unescaped ${{ sequence was found...` | 工作流内嵌 Python 字符串包含字面量 `${{`，被 GitHub Actions 当成表达式 | 将字面量拆成 `'$' + '{{'`，避免被 Action 解析器提前解释 |
| 修正版 | `python3: can't open file '.../custom/patch-repo/scripts/patch_weighted_balancer_with_stats.py'` | 自动提取原 WRR 步骤却没正确 checkout 其依赖脚本，且曾错误地把 `GITHUB_WORKSPACE` 视作嵌套 `custom` 路径 | 不再动态提取原 Action；显式把当前 `myxray` checkout 到 `patch-repo`，确保脚本存在 |
| V3 | `[patch] ERROR: required file not found: go.mod; run this script from Xray-core repository root` | WRR 脚本已经找到，但是在 Workspace 根目录运行，找不到相对路径的 `go.mod` | V4 中 `cd "$GITHUB_WORKSPACE/xray-core"` 后执行补丁；验证文件另用绝对路径写入 Workspace 根目录 |
| V4 | `--- FAIL: TestChinaSites`；`failed to open geosite.dat`；`stat ../../resources/geosite.dat: no such file or directory` | 只有 Linux AMD64 会运行 `go test ./app/router`；仓库测试资源缺少 GeoSite | V5 在测试前下载 `geosite.dat` 和 `geoip-lite.dat` 及 SHA256 文件，验证后将 `geoip-lite.dat` 重命名为 `geoip.dat` |
| V5 | 用户反馈 Artifact 上传成功，后上传 AMD64 ZIP | 至少构建/上传链路完成 | 解包校验并本机实际联合运行，详见 §6 |

> **重要排错规则**：那次 `TestChinaSites` 失败并非 Linux 的 Go 编译失败，亦非 AnyTLS/WRR 功能问题；而是 **Go 路由测试缺外部数据**。其他架构不运行 `go test ./app/router`，所以不遇到同一错误。不要通过删除测试来“假修复”。

### GeoData V5 处理要点

在 `xray-core` 根目录：

```bash
mkdir -p resources
BASE_URL='https://github.com/XTLS/Xray-rules-dat/releases/latest/download'
curl -fL --retry 3 "$BASE_URL/geosite.dat" -o resources/geosite.dat
curl -fL --retry 3 "$BASE_URL/geosite.dat.sha256sum" -o resources/geosite.dat.sha256sum
curl -fL --retry 3 "$BASE_URL/geoip-lite.dat" -o resources/geoip-lite.dat
curl -fL --retry 3 "$BASE_URL/geoip-lite.dat.sha256sum" -o resources/geoip-lite.dat.sha256sum
(
  cd resources
  sha256sum -c geosite.dat.sha256sum
  sha256sum -c geoip-lite.dat.sha256sum
  mv geoip-lite.dat geoip.dat
)
go mod download
go test ./proxy/anytls -count=1
go test ./app/router -count=1
```

当前用的是 `releases/latest`，不是固定版本；未来如上游资产名称/校验格式变化，要核对而不是盲目假设。日志中 `? github.com/xtls/xray-core/proxy/anytls [no test files]` 只说明该包无 Go 单元测试，不代表 AnyTLS 未编译；本机另做过端到端验证。

---

## 5. 本次会话涉及的上传包、产物和记录

**以下名称用于未来找回/重传；文件可能不随新会话自动挂载，不能假设旧 sandbox 路径在新会话依然有效。**

| 文件/路径名 | 用途与重要性 |
|---|---|
| `xray-anytls-linux-amd64-a52db8f6ed19.zip` | **独立 AnyTLS** 编译产物；最早验证 AnyTLS+TLS/REALITY 可连接 |
| `xray-wrr-anytls-linux-amd64-a52db8f6ed19.zip` | **最重要**：已实际验证的 Linux AMD64 三功能组合产物，含二进制/校验/构建记录 |
| `combined-validation/verification-report.md` | 三功能端到端完整验证摘要（源对话中生成） |
| `combined-validation/verification-evidence.zip` | 完整测试记录；包含 AnyTLS 传输、普通 WRR、WRR+AnyTLS TLS/REALITY 的日志 |
| `anytls-e2e-test-kit.zip` | 独立 AnyTLS 的回环测试脚本/说明 |
| `anytls_validation/full-results3.txt` | 独立 AnyTLS 的更多测试日志 |
| `xray-wrb-hys23-wrb10.1.4-nodes20261031-legacyperfdiag-rerelease-bundle (1).zip` | **最重要的旧 Manager 源码来源**：`source/xray-wrb/src/generator.go`、默认配置等 |
| `myxray-anytls/.github/workflows/build-anytls-xray.yml` | 独立 AnyTLS Action 归档 |
| `myxray-wrr-anytls/.github/workflows/build-wrr-selection-stats-anytls.yml` | **注意**：旧会话沙箱内这个文件是较早的 V3，不应当当作最新版使用 |
| `build-wrr-selection-stats-anytls-V5.yml` | 与**本恢复档案同时生成**的 V5 归档重建版；正文附录也包含完整 YAML |

#### 组合版 Artifact 的已检查记录

成功的 `xray-wrr-anytls-linux-amd64-a52db8f6ed19.zip` 中包含：

```text
xray-core/dist/xray-wrr-anytls-linux-amd64
xray-core/dist/xray-wrr-anytls-linux-amd64.sha256
xray-core/dist/build-info-linux-amd64.txt
wrr-validation.txt
```

- `build-info-linux-amd64.txt`：Xray commit `a52db8f6...`，AnyTLS commit `0721f9b...`，WRR patch commit `8fe9f7f...`。
- 原始 ELF 的 SHA256 与 ZIP 内 `.sha256` 一致：`6f98cbc113eb6a3b08dedeaa65a1c96d236dedde578e076e9c5025565f2fcb3c`。
- 二进制显示 `Xray 26.10.31 Custom (go1.27.3 linux/amd64)`。
- 这是一份 **Linux AMD64 二进制的证据**；用户还报告了 Linux ARM64 等其它矩阵的 CI 构建结果，但对其它架构未做实机端到端测试。

---

## 6. 已做的功能验证（不能与待测范围混淆）

测试证据对应 2026-11-05 生成的 `combined-validation/verification-evidence.zip` / `verification-report.md`。原地确认了二进制 SHA256 和构建记录。已记录以下本地回环测试：

| 用例 | 输入 | 结果 |
|---|---|---|
| 二进制完整性、启动 | ZIP 内 `.sha256`、ELF/version | SHA256 一致，Linux AMD64 可运行 |
| AnyTLS + TCP + TLS | SOCKS5 → Xray AnyTLS → 本地 HTTP | `HTTP 200`，响应体 `ANYTLS_LOOPBACK_OK /anytls-protocol-check` |
| AnyTLS + TCP + REALITY | 本机提供真实 TLS 伪装目标，经过 REALITY 握手 | `HTTP 200`，连接成功 |
| WRR 普通出站 | 两候选普通出站，权重 3:1，12 次请求 | 12/12 成功，选择次数 9:3 |
| WRR + AnyTLS + TLS | 两个 AnyTLS 出站，权重 3:1，12 次请求 | 12/12 成功，WRR 日志与 Stats API 结果均 9:3 |
| WRR + AnyTLS + REALITY | 两个 AnyTLS+REALITY 出站，权重 3:1，12 次请求 | 12/12 成功，WRR 日志与 Stats API 结果均 9:3 |
| WRR 出站回退异常 | 检查 `balancing strategy returns empty tag` | 此轮正确配置下 0 次 |
| 旧 WRB 的 WRR 正则写法 | `regexp: true`、`match`、`value`，`__xhm_` Tag | 12 次 AnyTLS 请求全成功，9:3，统计 API 对应 |
| 默认旧配置 | WRB 10.1.4 包的 `defaults/config.json` | 通过新组合核心的 `run -test` 配置校验 |
| `autoHealthWRR` 的依赖项 | `fallbackTag` 单独/联用 `observatory` | 单独缺 observatory 时校验失败，配套 observatory 后配置校验通过；**未做实际故障摘除/恢复** |

### 6.1 关键证据输出

**AnyTLS 会话**：

```text
proxy/anytls: anytls: new session created, seq=1
HTTP/1.0 200 OK
ANYTLS_LOOPBACK_OK /anytls-protocol-check
```

**真正的 WRR+AnyTLS StatsService 统计**（TLS / REALITY 两组单独测试的结果一致，每组 12 次）：

```json
{
  "stat": [
    {"name": "outbound>>>any-a>>>wrr>>>selections", "value": 9},
    {"name": "outbound>>>any-b>>>wrr>>>selections", "value": 3}
  ]
}
```

查询接口示例：`xray api statsquery --pattern=wrr`。可看到统计名称/数值与日志实际选中的节点吻合，不是简单的“配置能解析”。

### 6.2 已验证与尚未验证的边界

**可说**：上述固定版本的 Linux AMD64 组合核心在本机回环下三功能相容；真实加密 HTTP 传输成功，WRR/Stats 能调度 AnyTLS 节点。旧 WRB 的主要 WRR 配置字段/语法兼容。

**不能说已经证实**：公网连接抗检测、GFW 环境持久可用、跨客户端 sing-box/Mihomo 互通、长时间稳定性、内存/CPU 性能、故障摘除恢复、`autoWeightWRR` 动态更新、旧 WRB Manager 在 iKuai 实机部署的完整生命周期兼容、所有架构的运行时行为。`9:3` 是该轮 12 个样本的结果，不能作为大规模概率/负载行为的统计保证。

---

## 7. WRR JSON 必须保持的真实字段

重点是**不能把 WRR 的 `value` 写错成 `weight`、不能把 `match` 错写成 `tag`**。出站 `tag` 和权重规则的 `match` 属于不同位置。

### 7.1 简化的、已验证的权重配置

```json
{
  "type": "weightedRoundRobin",
  "settings": {
    "weights": [
      {"match": "any-a", "value": 3},
      {"match": "any-b", "value": 1}
    ]
  }
}
```

如果把 `value` 错写成 `weight`，曾经观察到“配置能被接受，但是策略返回空 tag，流量回退到默认出站”的假成功表现。正确检验方法必须同时看流量路由、计数器和错误日志。

### 7.2 来自旧版 WRB 10.1.4 的真实生成逻辑

原始配置**不是** `defaults/config.json` 中的静态 WRR。它由下面的旧包源码运行时生成：

```text
xray-wrb-hys23-wrb10.1.4-...-bundle.zip
└─ source/xray-wrb/src/generator.go
```

该文件约第 **425–440 行**，函数 `weightedRoundRobinStrategy(slots []Slot)`：

```go
weights = append(weights, map[string]any{
    "regexp": true,
    "match":  "^" + regexp.QuoteMeta(slot.GeneratedTag) + "$",
    "value":  slot.Weight,
})
return map[string]any{
    "type":     "weightedRoundRobin",
    "settings": map[string]any{"weights": weights},
}
```

关键含义：

1. `regexp: true`，而不是普通字符串匹配。
2. `match` 是 `^` 和 `$` 锚定的**精确 Tag 正则**；`regexp.QuoteMeta()` 会转义特殊字符。
3. `value` 对应权重，正整数；`GeneratedTag` 为空或权重 `< 1` 的节点不写入权重配置。
4. 同一 Manager 用 `weightedSelector(slots)` 生成 Balancer 的 `selector` 节点 Tag 列表。
5. 旧 Manager 的生成 Tag 可以是以 `__xhm_` 开头的自动节点名。
6. Proxy Balancer 在启用 `AutoHealthWRR` 时可能增加 `fallbackTag` 并创建 `observatory`；Direct 负载路径不应被普通健康摘除规则误操作。

兼容示例（重建示例，不是用户实际生产节点）：

```json
{
  "tag": "__xhm_proxy_balance",
  "selector": ["__xhm_proxy_a", "__xhm_proxy_b"],
  "strategy": {
    "type": "weightedRoundRobin",
    "settings": {
      "weights": [
        {"regexp": true, "match": "^__xhm_proxy_a$", "value": 3},
        {"regexp": true, "match": "^__xhm_proxy_b$", "value": 1}
      ]
    }
  }
}
```

**已验证兼容**：新组合 Xray 对此风格的 `regexp` 权重条目进行配置解析和实际轮询，并能处理 AnyTLS 候选出站；12 次请求获得 9:3，Stats API 一致。旧 Manager 的 WRR 生成逻辑本身**不需要因为 AnyTLS 而改变**。

**不应混淆的事**：旧 Manager 能生成的**现有 WRR 配置格式**兼容，≠ 旧 Manager 已经提供 AnyTLS 节点录入 UI、AnyTLS 配置生成器或全过程自动管理支持。若要让旧 Manager 新增 AnyTLS 节点类型，那是另一个开发需求，需要检查其 `types.go`、`generator.go`、UI、导入/订阅逻辑等。

### 7.3 `autoHealthWRR` 现状

- `generator.go` 在 Proxy WRR 分支可按条件给 Balancer 设置 `fallbackTag`。
- `ensureWRBAutoHealthObservatory` 创建/维护 `observatory` 健康监视器。
- 单独设置 `fallbackTag` 缺依赖会在配置校验时报错；和 `observatory` 配套时校验通过。
- **尚未测试**：节点被封/断线时是否按预期被摘除、恢复后是否自动加入、统计值是否连续正确、`autoWeightWRR` 是否会按延迟/健康动态更新。

---

## 8. 证据包结构与本地复核命令

`combined-validation/verification-evidence.zip` 至少包含以下文件（已核对条目）：

```text
verification-report.md
anytls-tls-reality-results.txt
wrr-plain-results.txt
wrr-anytls-tls-results.txt
wrr-anytls-reality-results.txt
```

关键可复核值（来自这份旧日志）：

```text
COMBINED_HTTP_SUCCESSES 12 ERRORS []
STATSQUERY_EXIT 0
COUNTS_FROM_ROUTE_LOG {'any-a': 9, 'any-b': 3}
ERROR_FALLBACK 0

REALITY_COMBINED_HTTP_SUCCESSES 12 ERRORS []
STATSQUERY_EXIT 0
COUNTS_FROM_ROUTE_LOG {'any-a': 9, 'any-b': 3}
ERROR_FALLBACK 0
```

如果下次能重新上传 AMD64 组合 Artifact，可使用以下简单命令恢复静态验证（先解压再按实际路径操作）：

```bash
unzip -l xray-wrr-anytls-linux-amd64-a52db8f6ed19.zip
unzip xray-wrr-anytls-linux-amd64-a52db8f6ed19.zip -d extracted
cd extracted/xray-core/dist
sha256sum xray-wrr-anytls-linux-amd64
cat xray-wrr-anytls-linux-amd64.sha256
chmod +x xray-wrr-anytls-linux-amd64
./xray-wrr-anytls-linux-amd64 version
```

注意：ZIP 中 `.sha256` 的记录路径是 `dist/xray-wrr-anytls-linux-amd64`，不等于从任意目录执行 `sha256sum -c` 都会通过；应对照实际解压路径，或手工比较哈希。不要拿 README 中未运行的命令替代实际连接实测。

如需恢复**真实回环验证**，优先重传测试包及二进制；仅有 `run -test`（配置检查）不足以证明能够建立会话、正确转发业务流量。

---

## 9. 接下来可以做的事情（按优先级）

1. **把当前基线锁定下来**：为通过测试的 Xray commit、AnyTLS commit、WRR patch commit 创建可追溯构建标签或记录；不要只依赖持续移动的 `main`。如果要升级 Xray，需要重新跑三功能测试。
2. **`autoHealthWRR` 故障注入测试**：两个 AnyTLS 节点正常 → 停止一个节点 → 确认 WRR 不再把业务分给故障节点 → 恢复节点 → 确认重新参与 WRR；同时核对 `fallbackTag` 与 observatory 状态。对真实请求成功率和 `statsquery` 同时断言。
3. **`autoWeightWRR` 测试**：由 Manager 修改节点权重，确认是否需要重新生成 Xray 配置、是否重启/热重载，以及实际选中次数与新的权重匹配。
4. **旧 WRB Manager 集成**：在测试环境中用 10.1.4 Manager 生成 Runtime JSON，交给组合核心启动；重点核对 iKuai 运行目录、GeoData、节点 Tag、observatory、DNS 路由、Manager 的 StatsService 读取逻辑。
5. **AnyTLS 第三方客户端互通**：sing-box/Mihomo → 组合版 AnyTLS 服务端，另测组合版客户端 → 其他服务端，含 TLS/REALITY/证书验证/版本差异。
6. **公网、长时间运行和性能**：多节点、较高并发、失败/断线/恢复、安全日志、内存和 CPU、网络不稳定时的重连策略。
7. **CI 可靠性**：移植变更通过源码定位锚点注入；官方升级可能造成接口冲突。将最新 `main` 构建与固定基线构建分开，避免突然失效。可加端到端本地 CI 测试，但不要将公网依赖引入必过单元测试。

### 下次提交问题时最有用的材料

- 本文档 + **当前 GitHub 仓库的真实工作流 YAML**（最好让接手模型读取最新源码，而非仅凭归档）。
- 构建运行链接及失败 Step 的完整日志（从第一处报错开始）。
- 有问题的 **Linux AMD64 ZIP**（含二进制、build-info、校验记录）。
- 若涉及旧 WRB Manager，再上传原 `...WRB10.1.4...bundle.zip` 或最新版本源码。
- 如问题涉及 AnyTLS 配置，上传**脱敏后的**入站/出站 JSON（删除真实私钥、UUID、密码、域名、IP 等敏感信息）。

---

## 10. 供新会话直接使用的接手提示词

> 我在维护 [WXMa1/myxray](https://github.com/WXMa1/myxray)，已有 Xray WRR + Selection Stats + AnyTLS 三功能组合核心。请先完整阅读我上传的《Xray + AnyTLS + WRR + Selection Stats 项目会话恢复档案》。在 Linux AMD64 上已通过 AnyTLS+TLS/REALITY、WRR 3:1、原生 Stats API 9:3、旧 WRB 10.1.4 正则权重语法的本地联合验证。当前基线 Xray `a52db8f6...`，AnyTLS `0721f9b...`，WRR patch `8fe9f7f...`。我会继续给你新的需求或 CI 日志。请优先参考真实仓库文件/日志，不要重做已经证实的功能；修 GitHub Action 时给我**完整 YAML 显示在聊天中**。区分配置验证、本机端到端验证和生产环境验证，尤其不要未经测试就宣称 autoHealthWRR 或 autoWeightWRR 已通过。

---

## 11. 附录：组合 Action V5 完整代码（归档版本）

> **说明**：这是依据本会话中 V5 工作流内容恢复的**归档重建稿**，保留其关键行为；它不是对 GitHub 当前文件的实时抓取，也不应在将来覆盖仓库中更高版本的修改。若继续开发，应先比对 GitHub 仓库的最新实际 `.github/workflows/build-wrr-selection-stats-anytls.yml`。在原会话中真正得到成功 Artifact 的是相同基线与相同功能的组合构建。

```yaml
# Xray-core + WRR + Selection Stats + AnyTLS
# V5: GeoData fix for Linux AMD64 routing tests
name: Build Xray with WRR + Selection Stats + AnyTLS

on:
  workflow_dispatch:
    inputs:
      xray_ref:
        description: 'XTLS/Xray-core ref'
        required: true
        type: string
        default: main

permissions:
  contents: read

jobs:
  build-combined:
    name: Combined / ${{ matrix.goos }}-${{ matrix.goarch }}
    runs-on: ubuntu-latest
    timeout-minutes: 55
    strategy:
      fail-fast: false
      matrix:
        include:
          - { goos: linux,   goarch: amd64, suffix: linux-amd64,   ext: '' }
          - { goos: linux,   goarch: arm64, suffix: linux-arm64,   ext: '' }
          - { goos: windows, goarch: amd64, suffix: windows-amd64, ext: '.exe' }
          - { goos: darwin,  goarch: amd64, suffix: darwin-amd64,  ext: '' }
          - { goos: darwin,  goarch: arm64, suffix: darwin-arm64,  ext: '' }
    steps:
      - name: Checkout original WRR patch repository
        uses: actions/checkout@v4
        with:
          path: patch-repo
          persist-credentials: false

      - name: Checkout official Xray-core
        uses: actions/checkout@v4
        with:
          repository: XTLS/Xray-core
          ref: ${{ inputs.xray_ref }}
          path: xray-core
          persist-credentials: false

      - name: Checkout pinned AnyTLS implementation
        uses: actions/checkout@v4
        with:
          repository: ynetlab/Xray-core
          ref: 0721f9b543a6c20f503c1ac181eeb27d98d808f2
          path: anytls-source
          persist-credentials: false

      - name: Check source revisions
        id: revisions
        shell: bash
        run: |
          set -euo pipefail
          expected='0721f9b543a6c20f503c1ac181eeb27d98d808f2'
          actual="$(git -C anytls-source rev-parse HEAD)"
          if [[ "$actual" != "$expected" ]]; then
            echo 'ERROR: AnyTLS source revision differs from pinned commit.' >&2
            exit 1
          fi
          upstream="$(git -C xray-core rev-parse HEAD)"
          echo "upstream=$upstream" >> "$GITHUB_OUTPUT"
          echo "upstream_short=${upstream:0:12}" >> "$GITHUB_OUTPUT"
          echo "Xray upstream: $upstream"
          echo "WRR patch repo: $(git -C patch-repo rev-parse HEAD)"
          echo "AnyTLS source: $actual"

      - name: Verify original WRR patch script
        shell: bash
        run: |
          set -euo pipefail
          script="$GITHUB_WORKSPACE/patch-repo/scripts/patch_weighted_balancer_with_stats.py"
          if [[ ! -f "$script" ]]; then
            echo "ERROR: WRR patch script missing: $script" >&2
            find patch-repo -maxdepth 3 -type f | head -60 >&2
            exit 1
          fi
          python3 -m py_compile "$script"
          echo "WRR patch script found: $script"

      - name: Apply original WRR + native selection-counter patch
        shell: bash
        run: |
          set -euo pipefail
          echo 'Applying WRR + Selection Stats patch...'
          (
            cd "$GITHUB_WORKSPACE/xray-core"
            test -f go.mod
            python3 "$GITHUB_WORKSPACE/patch-repo/scripts/patch_weighted_balancer_with_stats.py"
          )
          git -C xray-core add -N .
          git -C xray-core diff --check
          git -C xray-core diff --no-ext-diff --unified=0 > "$GITHUB_WORKSPACE/wrr-change.patch"
          git -C xray-core diff --name-only > "$GITHUB_WORKSPACE/wrr-changed-files.txt"
          if [[ ! -s "$GITHUB_WORKSPACE/wrr-changed-files.txt" ]]; then
            echo 'ERROR: WRR patch produced no source changes.' >&2
            exit 1
          fi
          if ! grep -Eiq 'weighted|wrr|round.?robin' "$GITHUB_WORKSPACE/wrr-change.patch"; then
            echo 'ERROR: WRR changes not detected.' >&2
            exit 1
          fi
          if ! grep -Eiq 'selection.{0,80}(stat|count)|(stat|count).{0,80}selection' "$GITHUB_WORKSPACE/wrr-change.patch"; then
            echo 'ERROR: Selection Stats changes not detected.' >&2
            exit 1
          fi
          {
            echo 'wrr_patch_script=scripts/patch_weighted_balancer_with_stats.py'
            echo "wrr_patch_commit=$(git -C "$GITHUB_WORKSPACE/patch-repo" rev-parse HEAD)"
            echo 'wrr_diff_markers=verified'
            echo 'selection_stats_diff_markers=verified'
            echo 'changed_files:'
            cat "$GITHUB_WORKSPACE/wrr-changed-files.txt"
          } > "$GITHUB_WORKSPACE/wrr-validation.txt"
          cat "$GITHUB_WORKSPACE/wrr-validation.txt"

      - name: Add AnyTLS to WRR-patched Xray
        shell: bash
        run: |
          set -euo pipefail
          test -f anytls-source/infra/conf/anytls.go
          test -f anytls-source/proxy/anytls/config.pb.go
          if [[ -e xray-core/proxy/anytls || -e xray-core/infra/conf/anytls.go ]]; then
            echo 'ERROR: Xray already contains AnyTLS.' >&2
            exit 1
          fi
          cp -a anytls-source/proxy/anytls xray-core/proxy/anytls
          cp anytls-source/infra/conf/anytls.go xray-core/infra/conf/anytls.go
          python3 - <<'PY'
          from pathlib import Path
          config = Path('xray-core/infra/conf/xray.go')
          content = config.read_text(encoding='utf-8')
          edits = [
              ('inboundConfigLoader = NewJSONConfigLoader(ConfigCreatorCache{',
               '\n\t\t"anytls": func() interface{} { return new(AnyTLSServerConfig) },'),
              ('outboundConfigLoader = NewJSONConfigLoader(ConfigCreatorCache{',
               '\n\t\t"anytls": func() interface{} { return new(AnyTLSClientConfig) },'),
          ]
          for anchor, addition in edits:
              if content.count(anchor) != 1:
                  raise SystemExit(f'ERROR: registration anchor changed: {anchor}')
              content = content.replace(anchor, anchor + addition, 1)
          config.write_text(content, encoding='utf-8')
          imports = Path('xray-core/main/distro/all/all.go')
          content = imports.read_text(encoding='utf-8')
          anchor = '_ "github.com/xtls/xray-core/proxy/blackhole"'
          if content.count(anchor) != 1:
              raise SystemExit('ERROR: distro import anchor changed')
          content = content.replace(
              anchor,
              '_ "github.com/xtls/xray-core/proxy/anytls"\n\t' + anchor,
              1,
          )
          imports.write_text(content, encoding='utf-8')
          PY
          cd xray-core
          gofmt -w infra/conf/xray.go infra/conf/anytls.go main/distro/all/all.go proxy/anytls/*.go
          git add -N infra/conf/anytls.go proxy/anytls
          git diff --check
          git diff --stat

      - name: Set up Go from Xray go.mod
        uses: actions/setup-go@v5
        with:
          go-version-file: xray-core/go.mod
          cache: true
          cache-dependency-path: xray-core/go.sum

      - name: Download GeoData and test AnyTLS + WRR + routing
        if: matrix.goos == 'linux' && matrix.goarch == 'amd64'
        working-directory: xray-core
        shell: bash
        run: |
          set -euo pipefail
          mkdir -p resources
          BASE_URL='https://github.com/XTLS/Xray-rules-dat/releases/latest/download'
          curl -fL --retry 3 "$BASE_URL/geosite.dat" -o resources/geosite.dat
          curl -fL --retry 3 "$BASE_URL/geosite.dat.sha256sum" -o resources/geosite.dat.sha256sum
          curl -fL --retry 3 "$BASE_URL/geoip-lite.dat" -o resources/geoip-lite.dat
          curl -fL --retry 3 "$BASE_URL/geoip-lite.dat.sha256sum" -o resources/geoip-lite.dat.sha256sum
          (
            cd resources
            sha256sum -c geosite.dat.sha256sum
            sha256sum -c geoip-lite.dat.sha256sum
            mv geoip-lite.dat geoip.dat
          )
          test -s resources/geosite.dat
          test -s resources/geoip.dat
          go mod download
          go test ./proxy/anytls -count=1
          go test ./app/router -count=1

      - name: Compile Xray with WRR + Stats + AnyTLS
        working-directory: xray-core
        shell: bash
        env:
          GOOS: ${{ matrix.goos }}
          GOARCH: ${{ matrix.goarch }}
          CGO_ENABLED: '0'
          XRAY_REF: ${{ inputs.xray_ref }}
        run: |
          set -euo pipefail
          mkdir -p dist
          binary="dist/xray-wrr-anytls-${{ matrix.suffix }}${{ matrix.ext }}"
          go build -trimpath -buildvcs=false \
            -ldflags='-s -w -buildid=' \
            -o "$binary" ./main
          sha256sum "$binary" > "$binary.sha256"
          {
            echo 'upstream_repo=XTLS/Xray-core'
            echo "upstream_ref=$XRAY_REF"
            echo "upstream_commit=${{ steps.revisions.outputs.upstream }}"
            echo 'anytls_source_repo=ynetlab/Xray-core'
            echo 'anytls_source_commit=0721f9b543a6c20f503c1ac181eeb27d98d808f2'
            echo 'wrr_patch=patch-repo/scripts/patch_weighted_balancer_with_stats.py'
            echo 'selection_stats=source_diff_verified'
            echo "wrr_patch_commit=$(git -C ../patch-repo rev-parse HEAD)"
            cat ../wrr-validation.txt
          } > "dist/build-info-${{ matrix.suffix }}.txt"

      - name: Smoke-test AnyTLS outbound config
        if: matrix.goos == 'linux' && matrix.goarch == 'amd64'
        working-directory: xray-core
        shell: bash
        run: |
          set -euo pipefail
          dist/xray-wrr-anytls-linux-amd64 version
          cat > /tmp/anytls-client-test.json <<'JSON'
          {
            "log": {"loglevel": "warning"},
            "outbounds": [
              {
                "protocol": "anytls",
                "settings": {
                  "address": "example.com",
                  "port": 443,
                  "password": "ci-test-only-password"
                },
                "streamSettings": {
                  "network": "tcp",
                  "security": "tls",
                  "tlsSettings": {"serverName": "example.com"}
                }
              }
            ]
          }
          JSON
          dist/xray-wrr-anytls-linux-amd64 run -test -c /tmp/anytls-client-test.json

      - name: Upload platform artifact
        uses: actions/upload-artifact@v4
        with:
          name: xray-wrr-anytls-${{ matrix.suffix }}-${{ steps.revisions.outputs.upstream_short }}
          path: |
            wrr-validation.txt
            xray-core/dist/xray-wrr-anytls-${{ matrix.suffix }}${{ matrix.ext }}
            xray-core/dist/xray-wrr-anytls-${{ matrix.suffix }}${{ matrix.ext }}.sha256
            xray-core/dist/build-info-${{ matrix.suffix }}.txt
          if-no-files-found: error
          retention-days: 14
```

---

## 12. 文档可信度/维护记录

- 此文档以**本次会话记录**及仍可读取的本地 Artifact ZIP、`build-info`、`wrr-validation.txt`、端到端日志、旧 WRB ZIP 中 `src/generator.go` 为依据。
- 已独立核对组合版 ZIP 内二进制哈希、构建版本记录、WRR 修改文件列表和测试证据日志。
- “WRB 旧配置验证通过”的动态测试结论来自本次会话先前的测试结果，附带明确的范围限制；不暗示整个 WRB Manager 已在生产环境验证。
- 附录 YAML 是归档复原版；**实际使用以用户当前仓库代码和持续集成记录为准**。
- 文件的本地 `/mnt/data` 路径、旧 Artifact URL 和下载缓存都有可能失效。恢复新会话时优先上传此 Markdown 与必要的 ZIP。

**到此为止：这是本次对话截至 2026-11-06 的可恢复状态。**
