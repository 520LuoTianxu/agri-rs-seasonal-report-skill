# 本 skill 附带的脚本

相对本 skill 目录。

## download/ — Sentinel 地块产品下载与出数
- `scripts/s1_s2_indices_pipeline.py` — 主流程：瓦片拉景、指数、共享图、地块 JSON
- `scripts/run_tile_shard.py` — 按分片跑瓦片
- `scripts/parcel_zonal_from_tile.py` — 瓦片栅格 → 地块分区统计
- `requirements.txt` / `README.md` / `config/*` — 依赖与配置模板（无密钥）

## oss_pg/ — 可选：OSS → Postgres
- `scripts/oss_to_pg.py`
- `sql/`、`requirements.txt`、`README.md`
- **不要**把含密钥的 `oss.env` 放进 skill

## report_pipeline/ — 分析出图与 PDF
- `run.py` — 入口
- `catalog.py` — 项目清单（交付前按用户项目改路径）
- `analyze.py` / `geo_figs.py` — 分析与出图
- `build.py` / `agent_load.py` / `harden_helpers.py` — 组装 PDF；优先读 agent 稿
- `data/agent_analysis/EXAMPLE_*.json` — agent 结论稿示例格式

运行前：把 `catalog.py` 与数据路径改成当前环境；CDSE/OSS/DB 凭据只用本机环境变量，勿写入本目录。
