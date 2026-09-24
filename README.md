# 红利 ETF 股息率与成分股监控

双基金静态看板：**03466.HK 恒生高息股 30 ETF**、**515080.SH 招商中证红利 ETF**。
支持基金切换、每日股息率与收盘价交互图、实际持仓比例、指数成分变更、资料日期和 CSV 下载。

- Version: `0.7.0`
- Updated: `2026-09-24 16:08 CST`
- 正式域名保持： https://03466-dividend.cw-info.top/
- 应用仍在 Quant VPS，沿用运行目录 `/opt/hk-03466-dividend-yield` 和 GitHub 仓库标识；页面及文档统一使用双基金名称。

## 数据与口径

| 基金 | 行情 | 分红 | 股息率 |
| --- | --- | --- | --- |
| 03466.HK | Data_Server `/v1/hk-equity-quotes`，全部来源按交易日校验 | 恒生投资官网上市 HKD 类别 3466 | 最近最多 12 次月息，不足 12 次按最近月息补足／未复权收盘价 |
| 515080.SH | 优先 Data_Server `/v1/cn-equity-quotes?market=SH&adjustment=raw`；缺口期间明确标注腾讯原始 `day` 日线临时来源 | Data_Server `/v1/cn-etf-distributions`，招商官网公告，元／10 份换算为元／份 | `(日期−365天, 日期]` 内实际现金分红之和／未复权收盘价，不按 12 次月息外推 |

首次除息前不绘制股息率；不使用前复权价、净值或指数股息率替代 ETF 现金分红率。港元和人民币独立显示。
行情必须读完整历史；任何同日收盘价冲突均停止该基金的更新，保留旧快照。两个基金独立执行，一方失败不阻止另一方。

03466 成分、持仓、主营业务继续直接取恒生指数、恒生投资和港交所官网，执行原有 30 条及代码集合一致性检查。
515080 的 100 只中证红利成分每日读取中证指数官方文件，基金持仓采用已核验中期报告的指数投资明细，指数权重独立展示其资料日期。报告持仓不是实时持仓；公司行业来自 Data_Server，目前尚无主营业务简介。

515080 数据缺口工单：`522b0258-c618-4ba0-b6e2-4a411d0f5d35`。当前临时来源不代表工单完成。详见 [数据契约](docs/project-docs/data-contract.md) 和 [来源证据](docs/project-docs/515080-source-evidence.md)。

## 本地运行与检查

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests -v
node --check app.js
python3 -m http.server 8088
```

访问 `http://127.0.0.1:8088/`，可用 `?fund=515080` 直接进入新增基金。

## 定时更新

Quant 使用北京时间；部署脚本安装两个独立任务：

```cron
5 18 * * 1-5 .venv/bin/python scripts/update-all.py
10 7 * * * .venv/bin/python scripts/update-all.py --constituents-only
```

`update-all.py` 分别调用两只基金的更新器。可单独运行 `scripts/update-data.py`（03466）或 `scripts/update-cn-data.py`（515080）。
页面先读取 `runtime-data/`，失败时使用 `assets/` 发布快照并明确提示。每个基金使用独立文件，不共用货币字段或持仓。

515080 报告持仓结果保存于 `assets/515080_disclosed_holdings.json`，包含报告链接、SHA-256、披露日、持仓日、明细与单位；新报告核验后通过 GitHub 更新该展示结果。日常指数同步不会把旧报告日期改为今天。

## 发布

本地验证 → 本次路径提交并推送 GitHub → Quant 拉取 → 部署并生成快照 → HTTP／浏览器验证。

```bash
git push
ssh quant
cd /opt/hk-03466-dividend-yield
git pull --ff-only
bash deploy/deploy-on-host.sh
```

部署脚本在项目 `.venv` 安装锁定依赖并配置原 nginx 站点；DNS、域名及证书位置不变。
HTML、JS、CSS 强制重新验证，JS/CSS 带发布版本；`runtime-data/` 返回 `no-store`。
