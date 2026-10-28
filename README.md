# 农情遥感季报（Cursor Agent Skill）

端到端农情遥感季报 skill：Sentinel-1/2 地块产品下载 →（可选）OSS 入库 → 分析出图 → 全季长势分析 PDF。

## 安装（Cursor / Grok Bot）

将本仓库克隆或复制到 agent skills 目录，保证存在：

```text
<skills-root>/agri-rs-seasonal-report-skill/SKILL.md
```

对话中可用 @ / 引用。相对路径均相对于本仓库根目录（`SKILL.md` 所在目录）。

## 目录

| 路径 | 说明 |
|------|------|
| `SKILL.md` | Skill 正文（YAML frontmatter + 流程） |
| `SCRIPTS.md` | 附带脚本清单 |
| `download/` | S1/S2 下载与地块产品脚本 |
| `oss_pg/` | 可选 OSS → Postgres |
| `report_pipeline/` | 分析出图与 PDF 流水线 |

**不含**：大地块 GeoJSON、fig 缓存、任何密钥（CDSE / OSS / DB 请用本机环境变量）。

## 注意

不要把密钥提交进本仓库。
