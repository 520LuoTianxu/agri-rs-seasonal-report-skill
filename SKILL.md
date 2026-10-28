---
name: 农情遥感季报
description: 端到端农情遥感季报：附带 S1/S2 下载脚本、OSS入库脚本、分析出图与 PDF 流水线；按项目写核心结论。
---
# 农情遥感季报（脚本 + 流程）

适用：下载 Sentinel 地块产品 →（可选）入库 → 分析出图 → 生成/改写全季长势分析 PDF。
本 skill **目录内已附带脚本**；运行前把 `catalog`/数据路径改成当前环境，凭据只用本机环境变量。

文件清单见 [`SCRIPTS.md`](SCRIPTS.md)。

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
| [`report_pipeline/catalog.py`](report_pipeline/catalog.py) | 项目清单（须改成本地数据路径） |
| [`report_pipeline/analyze.py`](report_pipeline/analyze.py)、[`geo_figs.py`](report_pipeline/geo_figs.py) | 分析与出图 |
| [`report_pipeline/build.py`](report_pipeline/build.py)、[`agent_load.py`](report_pipeline/agent_load.py)、[`harden_helpers.py`](report_pipeline/harden_helpers.py) | 组装 PDF；优先读 agent 稿 |
| [`report_pipeline/data/agent_analysis/EXAMPLE_p2784.json`](report_pipeline/data/agent_analysis/EXAMPLE_p2784.json) | 核心结论稿格式示例 |

**未附带**：大地块 GeoJSON、fig 缓存、含密钥的 env（禁止写入 skill）。
生产下载机任务队列可与 `download/` 二选一或衔接；勿把生产密钥写入本目录。

---

## 总流程

```
地块边界 / 项目清单
    ↓  download/scripts/…
① 下载与地块产品 → JSON/PNG（± OSS）
    ↓  可选 oss_pg/scripts/oss_to_pg.py
② report_pipeline/analyze.py + geo_figs.py
    ↓  撰写 data/agent_analysis/<key>.json
③ Agent 按项目写核心结论
    ↓  report_pipeline/build.py / run.py
④ PDF → 抽检 → 交付
```

缺哪段补哪段；已有数据可跳过下载。

---

## ① 下载要点

瓦片拉景一次 → 地块逐像素 JSON → 共享真彩/VV/VH URL 复用。产出 NDVI/NDRE 等 + clear；可选 S1。断点用 done 标记；上传失败可回填。并发忌内存打满；密钥不进 skill。

## ② 分析与出图要点

拔节前 NDVI、**拔节后 NDRE**；多期逐像素弱长势；持续弱≥2 期汇总；周边百分位；积温/降水；地图经纬度、约 10 m 像素、无平滑、无地块均值色。春/夏混种分季；弱地块按弱面积排序；混种「分组」列与行对齐。

## ③ 核心结论写法

按项目撰写，加厚、克制。只写已有证据（弱位置/抬升期、农事已记、无人机已见、末景边界、降水数字与时间是否接近）。禁止填空骨架、教方法、过度猜测、行动式巡田/对照建议、估产/财务/盐碱/待核实。建议段空则 build 整段不输出。加深受灾时间轴仅用户点名。

## ④ PDF 结构

核心结论 → 遥感比较 → 积温 → 分期弱长势与受损 →（有则）无人机 → 农事最后。无农事/无无人机整章省略且不提缺失。TOC 后仅 NDVI、NDRE。

---

## 交付与自检

按用户目录交付；常按省分文件夹；有无人机加 `_含无人机`。

- [ ] 下载脚本可跑或已有等价产品  
- [ ] analyze/geo_figs/build 路径已指向当前数据  
- [ ] 核心结论按项目、无行动建议、无猜因  
- [ ] 结构/NDRE/弱面积排名/禁项通过抽检
