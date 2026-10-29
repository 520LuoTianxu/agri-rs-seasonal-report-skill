---
name: 农情遥感季报
description: >-
  端到端农情遥感季报：附带 S1/S2 下载脚本、OSS入库、地块去重、弱地块受旱/受涝（S1+降雨，≥75%才入报告）、春夏
  force_season、省级综合分排行、分析出图与 PDF；按项目写核心结论。
---
# 农情遥感季报（脚本 + 流程）

适用：下载 Sentinel 地块产品 →（可选）入库 → **地块重叠去重** → 分析出图 → 弱地块受旱/受涝 → 生成/改写全季长势分析 PDF →（可选）省级综合分排行报告。
本 skill **目录内已附带脚本**；运行前把 `catalog`/数据路径改成当前环境，凭据只用本机环境变量。

文件清单见 [`SCRIPTS.md`](SCRIPTS.md)。省级排行细则见 [`report_pipeline/PROVINCE_SUMMARY.md`](report_pipeline/PROVINCE_SUMMARY.md)。

---

## 附带脚本（相对本 skill 目录）

### 下载：`download/`
| 路径 | 作用 |
|------|------|
| [`download/scripts/s1_s2_indices_pipeline.py`](download/scripts/s1_s2_indices_pipeline.py) | 主流程：瓦片拉景、S1/S2 指数、共享图、地块 JSON |
| [`download/scripts/run_tile_shard.py`](download/scripts/run_tile_shard.py) | 按分片跑瓦片 |
| [`download/scripts/parcel_zonal_from_tile.py`](download/scripts/parcel_zonal_from_tile.py) | 瓦片栅格 → 地块分区 |
| [`download/requirements.txt`](download/requirements.txt)、[`download/README.md`](download/README.md)、[`download/config/`](download/config/) | 依赖与配置模板（无密钥） |

### 可选入库：`oss_pg/`
| 路径 | 作用 |
|------|------|
| [`oss_pg/scripts/oss_to_pg.py`](oss_pg/scripts/oss_to_pg.py) | OSS 产品 → Postgres |
| [`oss_pg/sql/`](oss_pg/sql/) | 表结构与示例查询 |
| [`oss_pg/requirements.txt`](oss_pg/requirements.txt)、[`oss_pg/README.md`](oss_pg/README.md) | 依赖说明 |

### 报表流水线：`report_pipeline/`
| 路径 | 作用 |
|------|------|
| [`report_pipeline/run.py`](report_pipeline/run.py) | 入口 |
| [`report_pipeline/catalog.py`](report_pipeline/catalog.py) | 项目清单（须改成本地数据路径；`force_season`/`dedup`/`hazard`/`pixel_m` 等） |
| [`report_pipeline/parcel_dedup.py`](report_pipeline/parcel_dedup.py) | 圈地重叠去重 |
| [`report_pipeline/hazard_analyze.py`](report_pipeline/hazard_analyze.py) | 弱地块受旱/受涝（光学 + S1 + 降雨） |
| [`report_pipeline/analyze.py`](report_pipeline/analyze.py)、[`geo_figs.py`](report_pipeline/geo_figs.py) | 分析与出图 |
| [`report_pipeline/build.py`](report_pipeline/build.py)、[`cover.py`](report_pipeline/cover.py)、[`agent_load.py`](report_pipeline/agent_load.py)、[`harden_helpers.py`](report_pipeline/harden_helpers.py) | 封面 + 组装 PDF；优先读 agent 稿 |
| [`report_pipeline/province_summary.py`](report_pipeline/province_summary.py)、[`season_ring.py`](report_pipeline/season_ring.py) | 省级综合分排行与同季周边 |
| [`report_pipeline/PROVINCE_SUMMARY.md`](report_pipeline/PROVINCE_SUMMARY.md) | 综合分公式与排行硬规则 |
| [`report_pipeline/data/agent_analysis/EXAMPLE_p2784.json`](report_pipeline/data/agent_analysis/EXAMPLE_p2784.json) | 核心结论稿格式示例 |

**未附带**：大地块 GeoJSON、fig 缓存、含密钥的 env（禁止写入 skill）。

---

## 总流程

```
地块边界 / 项目清单
    ↓  download/scripts/…
① 下载与地块产品 → JSON/PNG（± OSS）
    ↓  可选 oss_pg/scripts/oss_to_pg.py
② catalog 开 dedup → parcel_dedup（启用优先、同状态较大 land_id）
    ↓  report_pipeline/analyze.py + geo_figs.py
③ 弱长势 → hazard_analyze（受旱光学 / 受涝 S1+降雨；≥75% 才入报告）
    ↓  撰写 data/agent_analysis/<key>.json（分条、蓝红绿着色）
④ report_pipeline/build.py / run.py → 项目 PDF
    ↓  可选 province_summary.py
⑤ 省级综合 PDF（综合分排行 + 近三年 + 卫星对比）→ 抽检 → 交付
```

缺哪段补哪段；已有数据可跳过下载。

**常跳过项目（除非用户点名）**：屯留、邓州、镇平。

**交付根目录**：`D:\农服工作\遥感全季度长势分析报告\{省}\`（大文件可经桌面中转再拷到 D 盘）。

---

## 地块重叠去重

`dedup=True` 且提供 `lands_json`（含 `land_id`/`land_status`）时，`analyze.load_cube` 自动执行：

1. 优先级：启用（status=1）压过停用（0）；同状态取 **更大 land_id**。
2. 高→低裁剪：每块 = 原边界 − 更高优先级并集。
3. 剩余 &lt;0.3 亩或内缩 5 m 为空 → **被合并**。
4. `make_valid`；`mu = area_m2 / 666.667`；`pixel_m` 重建 LAB（沈丘常用 20）。

产出：`*_parcels_dedup.json`、`*_parcels_merged.json`、`data/<key>_dedup_summary.json`。

---

## 作物识别：夏花生 vs 夏玉米（沈丘等）

地块名（`land_name`）含「花生」（含花生地/花生自种地/花生子种地等）→ **夏花生**，与夏玉米**分列统计、互不并亩**。

1. 从 `lands_*.json` 按名称筛花生 → 相对**全量圈地**跑与玉米相同的 `parcel_dedup` → 产出 `*_parcels_peanut.json` 等。
2. **报告启用口径**：只写 status=1 保留块的块数/亩数。
3. **禁止**把花生套进玉米拔节/NDRE 关键期弱长势表；花生用封垄/鼓粒与**收获光谱**。
4. 弱长势：仅在花生物候窗口可稳健定义时才做。受旱/受涝若对花生弱斑跑，同样 **≥75%** 才写入。
5. 核心结论第 1 点须写明两套作物；花生独立编号点。

---

## 春/夏玉米季节判定（`force_season`）

`analyze.classify_season` 默认用约 **06-15 NDVI 中位 ≥0.35** 标 spring、≤0.22 标 summer。

**板泉教训**：西高榆 6 月中旬残绿为**前茬土豆尚未收完**（不是春玉米；下一景常到 7-29，收后低谷在缺景里）。其他项目也可能是小麦残茬/杂草。不能只信 mid-June 绿度；**优先农事记载与区位物候**。

- `catalog` 项目可设 `force_season='summer'|'spring'`，`run_weak` 全项目覆盖自动分类。
- 纯春/纯夏项目：agent 正文写「春玉米」/「夏玉米」，**禁止**写「春夏混种」；省级榜只进对应一季。
- 真混种（如永济虞乡，农事明确春+夏）才保留混种分列。
- 常见覆盖（写入 `_FORCE_SEASON`）：
  - 夏玉米：板泉(`bq`)、孔村(`p451`)、南山南(`p828`)、西明义(`p970`)、定兴北七(`p633`) 等鲁南/冀中南平原。
  - 春玉米：张北(`p434`/`p436`)、怀安(`p539`/`p544`)、辽宁建平(`p119`) 等坝上/辽西。
- 改过 force 后须：`run_weak` → 改写 agent → 重出项目 PDF → 重跑 `province_summary`。

---

## 弱地块受旱 / 受涝

`hazard=True` 时对持续弱地块做灾害判读：

- **受旱**：光学 NDVI+NDMI/NDDI；冠层与降水前置条件防假旱。
- **受涝**：哨兵一号 VV/VH **并结合降雨**；仅 watch 时置信度封顶 &lt;75%。
- **硬门槛**：置信度 **≥75%** 才写入报告正文；更低只留 `data/<key>_hazard.json` 审计。

---

## 核心结论写法

按项目撰写，加厚、克制、分条清晰；重点数字/日期/风险用蓝/红/绿。只写已有证据。

**禁止**：行动式巡田/对照建议、估产/财务/盐碱/待核实、过度猜因。

**正文通俗化（硬规则）：**
- **不要写**「置信度≥75%」「才写入」等门槛话术，也不要写 NDVI/NDMI/NDDI、同月基线、冠层阈值等算法逻辑。
- **受旱/受涝**：内部仍用 ≥75% 筛选；正文只写**什么时候**受旱/受涝、**影响多少亩**。达不到门槛的不写、也不解释门槛。
- **周边对比**：禁止「第 N 百分位」；写成「超过周边约 N% 的同季耕地（偏低/差不多/略好/偏好）」——凡写「超过周边约 N%」须带「的地块」。`build.py` 用 `pct_plain`/`pct_verdict`。

## PDF 结构

封面 → 核心结论 → 遥感比较 → 积温 → 分期弱长势与受损 →（有则）无人机 → 农事最后。TOC 后仅 NDVI、NDRE（拔节后看 NDRE）。

---

## 省级综合报告（综合分排行）

入口：`report_pipeline/province_summary.py`。每省一份 `{省}遥感长势综合分析报告.pdf`：封面 + 加厚核心结论 + 分作物排行 + 高低名次项目级峰值卫星对比图。

### 大白话怎么算总分

总分 = 自家高峰分×一半 + 田里弱苗分×三成 + 周边升降分×两成。
哪项没有就跳过、剩下按比例摊。没有「超过周边」或没有今年高峰绿度 → 总分空着（—），不参与排名。

1. **自家高峰分**：把今年这块地绿得最旺时的数值，按 0.55～0.95 拉成 0～100 分。本来就高→高分，本来就低→低分；**不靠**「比去年涨了一点」抬分。
2. **田里弱苗分**：100 减去持续偏弱亩数占比。弱的少接近满分。
3. **周边升降分**：今年在周边里的位置减去前两年平均位置，在 50 分上下加减。比往年往前挤→加分，往后掉→减分。一直偏低但没更差≈中分。

**绝对「超过周边约 N% 的地块」只作描述列，不进总分。**

### 公式（与代码一致）

```
综合分 = (0.50×S_peak + 0.30×S_weak + 0.20×S_ringΔ) / 权重和

S_peak  = clip( (peak26 − 0.55) / (0.95 − 0.55) × 100 , 0, 100 )
S_weak  = max( 0 , 100 − 持续弱亩占比 )
S_ringΔ = clip( 50 + (rank%_26 − 近两年 rank% 均值) , 0, 100 )
```

缺某项权重归一；排序：综合分↓，同分再比 S_peak、S_weak、亩数。

### 春夏混种与同季周边（硬规则）

- 正文写「春夏混种」且能拆出春/夏亩数时：**同一项目拆两行**，分别进春玉米榜与夏玉米榜；亩数/块数/田内弱占比按季拆（不双计）。
- **周边对比必须同季**：春对春、夏对夏（`season_ring_rank.json`）；禁止混季或其他季顶替；算不出记 —。
- 近三年同地块峰值暂按全项目口径；相对周边三年对照用分季 `rank_pct`。
- 花生独立，无超过周边%/无峰值时综合分 —。

### 解读硬规则（一篇盖不全）

- **禁止**仅因「超过周边偏低」就写成「差」。
- 须对照近三年相对周边位置：差≤10 个百分点 → **区位常态**；明显低于往年 → **走弱**；明显高于 → **好转**。
- 排行加厚：写清靠前/靠后的证据（弱亩、同季周边、近三年峰值），并附高低名次项目卫星对比图。

### 运行

```bash
cd <report_pipeline 工作副本> && python3 province_summary.py
```

交付到 `D:\农服工作\遥感全季度长势分析报告\{省}\`。

---

## 交付与自检

- [ ] 下载脚本可跑或已有等价产品
- [ ] analyze/geo_figs/build 路径已指向当前数据
- [ ] 需要时已开去重，亩数/块数与摘要一致
- [ ] 春/夏已按农事+`force_season` 核对；板泉类残绿未误判春播
- [ ] 名含花生已按夏花生物候分列，未套玉米关键期、未并入玉米亩
- [ ] 受旱/受涝正文只写时间与亩数（内部≥75%筛选，不写门槛/算法）
- [ ] 核心结论按项目、有颜色、无行动建议、无猜因、无百分位/置信度话术
- [ ] 省级综合：综合分权重正确、绝对超过周边不入分、混种分列、同季周边
- [ ] 结构/NDRE/弱面积排名/禁项通过抽检；已拷到 D 盘对应省目录
