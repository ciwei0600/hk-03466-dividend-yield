# Deployment

Target: Quant VPS.

Default runtime path:

```text
/opt/hk-03466-dividend-yield
```

Deploy flow:

```text
local check -> commit -> push to GitHub -> Quant git pull -> install nginx config -> HTTP verify
```

Do not deploy by copying local files directly to Quant.

DNS is handled by the user. Until a domain is provided, verify with:

```text
http://03466-dividend.43.167.235.131.nip.io/
```
