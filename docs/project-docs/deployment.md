# Deployment

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
