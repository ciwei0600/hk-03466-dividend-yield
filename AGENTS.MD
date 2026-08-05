# hk-03466-dividend-yield — Codex 协作指引

## 项目描述

本项目是港股 03466.HK 日度年化 TTM 股息率与 HSHD30 成分股监控静态看板，展示折线图、关键指标、官网同步成分股、变更状态、计算口径和下载数据。

## 应用部署位置

- App 部署位置：Quant VPS
- 运行目录：`/opt/hk-03466-dividend-yield`
- 访问方式：DNS 由用户配置；当前先用 `03466-dividend.43.167.235.131.nip.io` 验证
- 结果库/展示库：无数据库，静态资产随版本发布

## 标准架构

- App 层部署在 Quant VPS。
- 所有基础/源数据必须来自 Data_Server 或已提交 Data_Server 工单后的临时可核验来源。
- 本项目只保存静态展示结果和可下载 CSV，不作为基础数据源。

## 目录规范

- 页面代码放在根目录静态文件和 `assets/`。
- `runtime-data/`、缓存、日志、导出文件必须 gitignore。
- 写代码不允许硬编码绝对路径，必须用相对路径、环境变量、配置文件或运行时推导路径。

## Data_Server 边界

- Data_Server API base: `http://100.77.62.83:8010`。
- 行情数据来自 Data_Server `/v1/hk-equity-quotes`。
- 港股 ETP 派息数据使用 Data_Server `/v1/hk-etp-distributions`；工单 `fcd695df-c1e0-4aa4-8ac5-617538509c8b` 已完成并通过接口/入库证据验证。
- HSHD30 成分股按用户明确要求直接使用恒生指数官网 `hshd30/constituents.do` 公开接口，每天 `07:10 CST` 查询一次；严格校验 series code、30 条数量和代码唯一性，异常时不得覆盖上一次成功快照。
- 成分股 Data_Server 工单 `471ba741-c8c2-4165-b78a-0d5b35273725` 已按该决定拒绝，不作为项目依赖。
- `submitted/approved` 不是完成；只有 `done` 且通过真实接口或入库验证才算补齐。
- 所有判断必须有事实依据，不能靠猜测。

## 部署流程

- 本地测试通过后，必须先提交并推送到 GitHub。
- 部署端只能从 GitHub 拉取或下载代码部署。
- 绝对不允许从本机直接 `scp`、`rsync`、`tar`、复制代码到服务器后部署。
- 如果服务器还没有 GitHub 拉取能力，先配置只读 deploy key 或等价 GitHub 拉取方式。
- 部署后必须验证：`git rev-parse` / `git status`、nginx 状态、HTTP 页面。

## 安全规则

- 删除整个目录前必须询问用户。
- 不要提交密钥、token、真实数据库密码。
- `.env.example` 只放变量名和示例值。
