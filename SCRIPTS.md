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
- `catalog.py` — 项目清单（含 `force_season`；交付前改路径）
- `analyze.py` / `geo_figs.py` — 分析与出图
- `parcel_dedup.py` — 圈地重叠去重（status + land_id）
- `hazard_analyze.py` — 弱地块受旱/受涝（≥75% 才入报告）
- `build.py` / `cover.py` / `agent_load.py` / `harden_helpers.py` — 组装 PDF（封面 + agent 稿）
- `province_summary.py` / `season_ring.py` — 省级综合分排行与同季周边
- `PROVINCE_SUMMARY.md` — 综合分公式与排行硬规则
- `data/agent_analysis/EXAMPLE_*.json` — agent 结论稿示例格式
- `data/season_ring_rank.json` — 混种同季周边排名缓存

运行前：把 `catalog.py` 与数据路径改成当前环境；CDSE/OSS/DB 凭据只用本机环境变量，勿写入本目录。


## 地块重叠去重（parcel_dedup）

模块：`report_pipeline/parcel_dedup.py`，由 `analyze.load_cube` 在 catalog 设置 `dedup=True` 且提供 `lands_json` 时自动执行。

规则（沈丘 group 2878 已确认）：
1. 优先级：`land_status=1`（启用）压过 `0`（停用）；同状态取 **更大 land_id**。
2. 高→低依次裁剪：每块保留 `原边界 − 更高优先级边界并集`；重叠只归高优先级。
3. 裁后剩余 &lt; **0.3 亩**，或 `buffer(-5m)` 为空 → **被合并**（不进入 keep）。
4. 面积：投影坐标系下 `mu = area_m2 / 666.667`；几何 `make_valid`。
5. 栅格：`rasterize_lab` 按 keep 顺序写入空像元（高优先级先占）。像素分辨率用 catalog `pixel_m`（沈丘为 20）。

产出：`*_parcels_dedup.json`、`*_parcels_merged.json`、`data/<key>_dedup_summary.json`；分析用去重后 PL/LAB。

## 弱地块受旱 / 受涝（hazard_analyze）

模块：`report_pipeline/hazard_analyze.py`（`run.py` 在弱长势后可选调用；catalog `hazard=True`）。

- **受旱**：复用 `agric_satellite_analysis_common.agri_classify` 的 `classify_drought_series`（NDVI+NDMI/NDDI + 同月基线）。报告侧额外要求冠层 NDVI≥0.4，且前 14 日降水合计≤50 mm（抑制裸地/雨季假旱）。
- **受涝**：同库 `classify_flood_series`（S1 VV/VH 相对同轨基线 + VH helper）；再与前后 3 日降水联合打分。仅 `watch` 时置信度封顶 &lt;75%。
- **硬门槛**：置信度 **≥75%** 才写入报告/核心结论；低于 75% 只留 `data/<key>_hazard.json` 审计，正文不写受旱/受涝结论。
- 沈丘可复用 `/workspace/project2878_20261019/flood/flood_indices_per_parcel.csv` 与 `rain_*.json`（catalog `flood_csv` / `rain_glob`）。

### 正文写法

去重后核心结论与汇总数字**只写去重后的地块数与亩数**，不要再写去重前的原始块数/亩数对照。

## 夏花生（名含「花生」）

- 识别：`lands` / 地块名含「花生」。与夏玉米分列；正文启用亩不并入玉米去重亩。
- 去重：同 `parcel_dedup`，建议相对全量圈地削边后再滤花生；启用 status=1 为报告口径（沈丘例：41 块 / 583.9 亩）。
- 物候：麦后夏花生，6 月上旬播，8–9 月封垄，NDVI 峰值≈0.89；收获约 9 下旬–10 中下旬。
- **禁止**套用玉米拔节/NDRE 关键期弱长势表；用花生收获规则（裸土/晾晒/落黄，见离线 `peanut.py` / `design_peanut_harvest.md`）。
- 产出示例：`*_parcels_peanut.json`、`*_parcels_peanut_dedup.json`、`data/<key>_peanut_dedup_summary.json`；结论写入 `data/agent_analysis/<key>.json`。


## 2026-10-28 正文通俗化
- 核心结论禁置信度/算法话术；受旱涝只写时间+亩数。
- 「第 N 百分位」→「超过周边约 N% 的地块（偏低/差不多/略好/偏好）」。

## 省级综合报告
- 入口：`province_summary.py`；细则见同目录 `PROVINCE_SUMMARY.md`。
- 综合分 = 0.50×同地块近三年分 + 0.30×田内分 + 0.20×相对周边变化分；绝对「超过周边」不入分。
- 春夏混种拆两行进对应榜；周边春对春、夏对夏。
- 交付：`D:\农服工作\遥感全季度长势分析报告\{省}\`；常跳过屯留/邓州/镇平。
