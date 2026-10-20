# Trading Strategy · Public research edition

公开版研究代码、原创中文观点摘要、已存数值结果和原始来源链接。它是新建的独立公开副本，不包含旧归档的 Git 历史。

## 内容

- **市场访谈**：复用现有的 [市场访谈观点审计公开版](https://github.com/attm-agenticcoding/market-calls-audit-public)，这里不重复打包访谈档案。
- **Crypto 观点**：[快照摘要](reports/SNAPSHOT.md) 与 [结构化结果](data/crypto-calls.json)。原始作者身份由公开账号和来源链接说明，中文概述是研究者转述。
- **动量回测**：[已存指标](data/momentum-metrics.json)、[公开来源](data/sources.json) 和独立的资本利得／亏损结转算术。全部金额属于假设回测，不是私人账户。
- **研究工具**：固定期限方向情景、缺失数据处理和公开 OHLC 校验。只使用 Python 标准库。

## 本地核验

Python 3.10 或以上，无需安装依赖。测试离线，不请求行情、不运行交易、不创建云端任务：

```sh
python3 -m unittest discover -s tests
python3 scripts/check_public.py
python3 scripts/summarize.py
```

行情读取代码保留作可选研究工具，只有手动执行才访问公开接口；它不需要 API key。下载结果写入忽略目录，不会自动发布：

```sh
python3 research/fetch_prices.py --symbols BTC ETH --start 2026-10-01 --end 2026-10-10
```

## 能复现什么

可离线复算公开结果的计数、已给入场／离场价的方向收益，运行方法边界测试；有自己的合法日价输入时，可调用 `research.scenarios.evaluate` 复算固定期限情景。

**不能从本仓库完整重建历史档案或完整动量回测。** 原始第三方全文、转录、推文全集、行情原始响应、完整股票面板和旧归档载荷均未带入。公开接口的历史覆盖及可用性也可能变化。已存结果不等于本次重新计算结果，不完整资料继续视为缺口。

详见 [研究方法与限制](docs/METHODOLOGY.md)、[公开范围](docs/PUBLIC_SCOPE.md) 和 [权利说明](RIGHTS.md)。本仓库没有配置 Actions、自动同步或生产发布。
