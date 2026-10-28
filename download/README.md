# 农业瓦片 S1/S2 → 地块指标 资源包

**当前状态：只打包，不跑数（`do_not_run_yet=true`）。**

## 目标

1. 以 **虚拟项目区 / 5×5 km 瓦片**（`tile_id`）为拉取单元，从微软 Planetary Computer 拉 Sentinel-2 L2A + Sentinel-1 RTC。  
2. 计算业务指标并写 JSON：  
   - S2：NDVI / NDMI / NDRE / EVI / CIre / MNDWI  
   - S1：VV/VH（linear + dB）及比值  
3. 再把结果 **拆到每个地块边界**（parcel polygon 掩膜后的像元统计）。  
4. 三台机器各跑一个 GeoJSON 分片（无重叠）。

## 目录

```
data/full/tiles_all.geojson      # 6158 瓦片全量
data/full/parcels_all.jsonl      # 14050 地块属性（无坐标）
data/full/parcels_geoms.geojson  # 【需你补】地块多边形
data/shards/shard_0{1,2,3}.geojson
config/machines.yaml
config/metrics.yaml
config/manifest.json
scripts/s1_s2_indices_pipeline.py   # 单点 AOI 拉取+指标
scripts/run_tile_shard.py           # 按分片跑瓦片
scripts/parcel_zonal_from_tile.py   # 瓦片→地块
output/machine-{1,2,3}/             # 运行产物
```

## 三机分工

| 机器 | 分片 | 瓦片数 |
|------|------|--------|
| machine-1 | shard_01.geojson | 2053 |
| machine-2 | shard_02.geojson | 2052 |
| machine-3 | shard_03.geojson | 2053 |

## 能否做到「地块边界像素值」？

**能，但缺地块多边形。**  
`parcels_all.jsonl` 只有 `parcel_id` / 面积 / 名称等属性，**没有 geometry**。  
要做真正的地块掩膜统计，请导出 `data/full/parcels_geoms.geojson`（字段至少含 `parcel_id`，最好有 `tile_id`）。

在补齐多边形之前：

- 可以先按瓦片跑通 S1/S2 指标 JSON（虚拟项目区维度）  
- 地块级只能做属性关联，不能做边界内像元聚合

## 推荐运行顺序（就绪后）

```bash
pip install -r requirements.txt

# 每台机器先 dry-run
python3 scripts/run_tile_shard.py --shard 01
python3 scripts/run_tile_shard.py --shard 01 --limit 1 --run   # 小试

# 地块拆分（需 parcels_geoms.geojson）
python3 scripts/parcel_zonal_from_tile.py --machine 1
python3 scripts/parcel_zonal_from_tile.py --machine 1 --run
```

## 产出形态

- `output/machine-X/tiles/<tile_id>/meta/s2_indices.json`  
- `output/machine-X/tiles/<tile_id>/meta/s1_indices.json`  
- `output/machine-X/parcels/parcel_metrics.jsonl`  
  每行一个地块，含 S1/S2 时序统计（掩膜后 mean/median/分位数等）

可选：真彩 PNG（`--s2-rgb`）；OSS 上传可接已有 `mall-sld-test` 配置。

## 质量说明（三机一致）

三台使用同一套脚本与 `config/metrics.yaml`，仅 `shard` 不同，保证指标定义、波段、SCL 掩膜、分辨率一致。
