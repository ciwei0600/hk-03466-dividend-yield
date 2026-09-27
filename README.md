# 红利 ETF 股息率与成分股监控

双基金静态看板：**03466.HK 恒生高息股 30 ETF**、**515080.SH 招商中证红利 ETF**。
支持基金切换、每日股息率与收盘价交互图、拖动日期与区间选择、实际持仓比例、指数成分变更、资料日期和 CSV 下载。

- Version: `0.8.0`
- Updated: `2026-09-27 10:34 CST`
- 正式域名保持： https://03466-dividend.cw-info.top/
- 应用仍在 Quant VPS，沿用运行目录 `/opt/hk-03466-dividend-yield` 和 GitHub 仓库标识；页面及文档统一使用双基金名称。

## 数据与口径

| 基金 | 行情 | 分红 | 股息率 |
| --- | --- | --- | --- |
| 03466.HK | Data_Server `/v1/hk-equity-quotes`，全部来源按交易日校验 | 恒生投资官网上市 HKD 类别 3466 | 最近最多 12 次月息，不足 12 次按最近月息补足／未复权收盘价 |
| 515080.SH | 优先 Data_Server `/v1/cn-equity-quotes?market=SH&adjustment=raw`；缺口期间明确标注腾讯原始 `day` 日线临时来源 | Data_Server `/v1/cn-etf-distributions`，招商官网公告，元／10 份换算为元／份 | 每笔分红平摊到相邻除息日之间的交易日；过去12个月摊分额合计／未复权收盘价 |

515080 展示“交易日摊分 TTM 股息率”：每笔分红平摊到上次除息日之后、本次除息日（含）的实际交易日；首次自上市日起摊分，周末和休市日不计。TTM取过去12个月的交易日摊分额合计，不固定套用250/252个交易日；上市不足一年留空，价格仍完整展示。

已完成分红区间事后回填、画实线；最新未完成区间沿用上一期每交易日分红估算，含估算的TTM画虚线，实际分红到齐后自动回填并转实线。浮窗和读数展示估算状态。历史摊分不能视为当时已知分红或用于无前视偏差的买点回测；它是股息率，不是包含价差的总收益率，价格波动仍会影响股息率。

下载CSV包含每日摊分额、分红区间、交易日数量及TTM估算金额/天数；`actual_365d_*`保留严格365天实际现金分红。03466口径沿用最近最多12次月息补足年化；首次除息前仅股息率留空。两基金均使用真实未复权收盘价，港元和人民币独立显示。
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

点击图表可在浮窗查看选中日期、对应股息率和收盘价（含币种）；浮窗跟随选中日期更新并限制在图表与屏幕内，点击图表面板外或按Esc关闭。两只基金均支持电脑点击、键盘Enter与手机触摸。

图表下方可拖动两端调整日期区间、拖动中间平移，也可选择近1月、3月、1年或全部。日期滑块及左右按钮按交易日移动选中点，图表与读数同步；键盘方向键可操作，手机支持触摸拖动。切换基金时重置为该基金完整区间，顶部始终显示最新交易日指标。

## 定时更新

Quant 使用北京时间；部署脚本安装两个独立任务：

```cron
5 18 * * 1-5 .venv/bin/python scripts/update-all.py
10 7 * * * .venv/bin/python scripts/update-all.py --constituents-only
```

`update-all.py` 分别调用两只基金的更新器。可单独运行 `scripts/update-data.py`（03466）或 `scripts/update-cn-data.py`（515080）。
页面先读取 `runtime-data/`，失败或515080计算方法版本不匹配时使用 `assets/` 发布快照并明确提示。每个基金使用独立文件，不共用货币字段或持仓。

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

仅更新计算口径时，可运行 `.venv/bin/python scripts/update-cn-data.py --recalculate`，复用既有已核验未复权收盘价、刷新官方分红后重算515080；必须有日期及行数匹配的逐日CSV与summary，保留原行情快照时间。正常定时更新仍重新获取行情。

部署脚本在项目 `.venv` 安装锁定依赖并配置原 nginx 站点；DNS、域名及证书位置不变。
HTML、JS、CSS 强制重新验证，JS/CSS 带发布版本；`runtime-data/` 返回 `no-store`。
