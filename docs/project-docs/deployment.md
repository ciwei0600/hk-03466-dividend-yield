# 红利 ETF 双基金看板部署

Target: Quant VPS.

Public URL:

```text
https://03466-dividend.cw-info.top/
```

Default runtime path:

```text
/opt/hk-03466-dividend-yield
```

Deploy flow:

```text
local check -> commit -> push to GitHub -> Quant git pull -> install nginx config -> HTTP verify
```

Do not deploy by copying local files directly to Quant.

运行依赖：部署脚本创建 `.venv` 并安装 `requirements.txt`。两只基金由 `scripts/update-all.py` 独立更新；07:10成分、18:05工作日行情。原域名、目录和nginx站点标识保持兼容。
