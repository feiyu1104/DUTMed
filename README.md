# DUTMed — 基于 Neo4j + LLM 的多模态医学问答系统

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)![Neo4j](https://img.shields.io/badge/Neo4j-Compatible-brightgreen?logo=neo4j)![SAM](https://img.shields.io/badge/SAM-Segment_Anything_Model-7A4FFF?logo=pytorch&logoColor=white)![Flask](https://img.shields.io/badge/Flask-2.0%2B-orange?logo=flask)
![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)![Status](https://img.shields.io/badge/Status-Active-brightgreen)![Last Commit](https://img.shields.io/github/last-commit/feiyu1104/DUTMed?color=blue)![Repo Size](https://img.shields.io/github/repo-size/feiyu1104/DUTMed?color=orange)

---

**DUTMed** 是一个结合 **知识图谱（Neo4j）** 与 **大语言模型（阿里云通义千问)** 的智能医学问答助手，支持**文本问答、图像分析**，适用于医学教育、临床辅助、科研探索等场景。 

![界面](img/界面.png)

## 🌟 核心功能

- ✅ **智能问答**：基于医学知识图谱 + LLM，精准回答疾病、症状、药品、检查等问题
- ✅ **多跳推理**：支持单跳/多跳查询，深入挖掘关联实体
- ✅ **预算控制**：支持 `Deep` / `Deeper` 模式，平衡速度与深度
- ✅ **图像理解**：上传医学图像 → 自动分割 → AI 影像描述 → 摘要提炼 → 关联知识图谱
- ✅ **文档入库**：上传 TXT / JSON / MD 等格式文件→ 自动切片、LLM 抽取实体关系、写入 Neo4j，文档切片作为参考资料
- ✅ **多轮对话**：浏览器 Session 级别的对话记忆，支持指代消解与上下文连贯问答
- ✅ **流式响应**：实时显示思考过程，透明可解释
- ✅ **快速使用**：提供交互式前端，可一键部署使用

## 🚀 快速开始

### 1. 克隆项目

```bash
git clone https://github.com:feiyu1104/DUTMed.git
cd DUTMed
```

### 2.安装依赖

```bash
pip install -r requirements.txt
```

### 3.数据导入

```bash
# 安装依赖
pip install neo4j==5.14.1
# 确保Neo4j数据库已启动
# 默认连接信息：
# URI: bolt://localhost:7687
# 用户名: xxx
# 密码: xxxxx
python neo4j_import.py # 运行脚本将数据导入Neo4j中，需要等待十几分钟
```

### 4.配置环境变量

创建.env文件：

```env
# Neo4j 数据库配置
NEO4J_URI=your_url_here
NEO4J_USER=your_name_here
NEO4J_PASSWORD=your_password_here

# 阿里云通义千问 API
ALI_API_KEY=your_api_key_here
ALI_BASE_URL=https://dashscope.aliyuncs.com/api/v1
ALI_MODEL0=qwen-plus        # 用于实体识别、答案生成、文档抽取、影像摘要
ALI_MODEL1=qwen-vl-plus     # 用于医学图像描述（多模态）

# 可选：文件上传大小限制（单位 MB，默认 50）
# MAX_UPLOAD_MB=50

# 可选：对话记忆保留时长（单位小时，默认 2）
# SESSION_MAX_AGE_HOURS=2
```

> 💡 如无阿里云账号，可替换为其他 LLM API（如 OpenAI、本地模型），需修改 `q_a.py` 中 `call_llm` 方法。

### 5.启动应用

```bash
python app.py
```

访问 👉 [http://localhost:5001 ](http://localhost:5001/)即可使用！

## 🧭 使用说明

本项目支持 **Web 界面交互** 和 **终端命令行问答** 两种模式，满足不同场景需求：

### 1.Web 界面模式

适合：演示、团队协作、非技术人员使用
特点：图形化界面、支持图像上传与文档入库、多轮对话记忆、实时日志流、模式切换

#### 启动方式：见🚀 快速开始

#### 工具栏说明

| 按钮/控件 | 功能 |
|-----------|------|
| 🧠 深度搜索 (多跳/单跳) | 切换多跳推理模式 |
| 🗑️ 清除记忆 | 清除当前会话对话历史，开启新会话 |
| 搜索预算 Deep / Deeper | 控制知识图谱查询范围与深度 |
| 📎 上传图片 | 上传医学图像，自动分割 → 描述 → 摘要 → 知识图谱关联分析 |
| 📄 上传文档 | 上传 TXT/JSON/MD/CSV/PDF，自动抽取实体关系写入 Neo4j |

### 2. 终端命令行模式

适合：快速测试、批量问答、脚本集成、无 GUI 环境
特点：轻量、快速、支持参数控制、无依赖前端

#### 启动方式：

```bash
# 默认模式（多跳 + Deeper）
python q_a.py

# 多跳 + Deeper
python q_a.py --search_budget Deep

# 禁用多跳 + Deep 模式（轻量快速）
python q_a.py --disable_multi_hop --search_budget Deep

# 禁用多跳 + Deeper 
python q_a.py --disable_multi_hop
```

### 3.模式对比表

|          |                    |                           |
| -------- | ------------------ | ------------------------- |
| 启动命令 | `python app.py`    | `python q_a.py [参数]`    |
| 交互方式 | 浏览器图形界面     | 终端命令行问答            |
| 图像支持 | ✅ 支持上传与分割   | ❌ 仅文本问答              |
| 实时日志 | ✅ 可视化“思考过程” | ✅ 终端彩色输出（Rich 库） |
| 模式切换 | ✅ 界面按钮/下拉框  | ✅ 命令行参数              |

## 🎥 使用演示

### 1.Web 界面模式

- ### 文本问答

![界面](img/正常问答.png)

- ### 影像分析

![界面](img/影像切割.png)
![界面](img/影像问答.png)

- ### 用户历史信息问答

![界面](img/用户历史信息.png)

- ### 文档入库

![界面](img/文档.png)

### 2. 终端命令行模式

![界面](img/4.png)

![界面](img/5.png)

## 🛠️ 技术架构

![界面](img/架构图.png)

```
Frontend (HTML/CSS/JS)
     ↓ SSE / Fetch
Flask (app.py)
     ├── /ask          问答接口（SSE 流式）
     ├── /upload_image 图像上传接口
     ├── /upload_document 文档上传接口
     └── /clear_history 清除对话记忆
     ↓
Neo4jRAGSystem (q_a.py)
     ├── 多轮对话改写（指代消解）
     ├── 实体关系抽取（LLM）
     ├── 知识图谱查询（Neo4j）
     │    ├── 一跳查询 + Embedding 相似度排序
     │    ├── 多跳推理（可选）
     │    └── SourceChunk 原文片段检索
     └── 答案生成（LLM + 对话历史注入）
     ↓
图像模块
     ├── 图像分割（FastSAM）        → image_segmentation.py
     ├── 图像描述（Qwen-VL）        → image_description.py
     └── 影像摘要（Qwen-Plus）      → image_description.py
     ↓
文档入库模块（document_ingestion.py）
     ├── 文本切片（800字/120重叠）
     ├── 实体关系抽取（LLM）
     └── 写入 Neo4j（SourceDocument / SourceChunk / 实体节点）
```

## 📊 数据说明

数据文件见`data/症状.json`文件，其包含了丰富的疾病信息，每条记录包含24个字段的医疗数据。

### 1.节点类型（9种）

| 节点类型 | 标签         | 描述               | 示例                         |
| -------- | ------------ | ------------------ | ---------------------------- |
| 疾病     | `Disease`    | 疾病信息（主节点） | 肺炎、糖尿病、高血压         |
| 分类     | `Category`   | 疾病分类           | 内科、呼吸内科、心血管内科   |
| 症状     | `Symptom`    | 疾病症状           | 发热、咳嗽、胸痛             |
| 科室     | `Department` | 治疗科室           | 内科、外科、急诊科           |
| 治疗方法 | `Treatment`  | 治疗方式           | 药物治疗、手术治疗、康复治疗 |
| 检查项目 | `Check`      | 诊断检查           | 血常规、胸部CT、心电图       |
| 药物     | `Drug`       | 药物信息           | 阿奇霉素、青霉素、布洛芬     |
| 食物     | `Food`       | 食物信息           | 鸡蛋、牛奶、辣椒             |
| 食谱     | `Recipe`     | 推荐食谱           | 百合粥、银耳汤、蒸蛋羹       |

### 2.关系类型（11种）

| 关系类型             | 描述               | 示例                                   |
| -------------------- | ------------------ | -------------------------------------- |
| `BELONGS_TO`         | 疾病属于某分类     | (肺炎)-[:BELONGS_TO]->(呼吸内科)       |
| `HAS_SYMPTOM`        | 疾病有某症状       | (肺炎)-[:HAS_SYMPTOM]->(发热)          |
| `TREATED_BY`         | 疾病由某科室治疗   | (肺炎)-[:TREATED_BY]->(呼吸内科)       |
| `USES_TREATMENT`     | 疾病使用某治疗方法 | (肺炎)-[:USES_TREATMENT]->(药物治疗)   |
| `REQUIRES_CHECK`     | 疾病需要某检查     | (肺炎)-[:REQUIRES_CHECK]->(胸部CT)     |
| `RECOMMENDS_DRUG`    | 疾病推荐某药物     | (肺炎)-[:RECOMMENDS_DRUG]->(阿奇霉素)  |
| `COMMONLY_USES_DRUG` | 疾病常用某药物     | (肺炎)-[:COMMONLY_USES_DRUG]->(青霉素) |
| `SHOULD_EAT`         | 疾病宜吃某食物     | (肺炎)-[:SHOULD_EAT]->(鸡蛋)           |
| `SHOULD_NOT_EAT`     | 疾病不宜吃某食物   | (肺炎)-[:SHOULD_NOT_EAT]->(辣椒)       |
| `RECOMMENDS_RECIPE`  | 疾病推荐某食谱     | (肺炎)-[:RECOMMENDS_RECIPE]->(百合粥)  |
| `ACCOMPANIES`        | 疾病伴随其他疾病   | (糖尿病)-[:ACCOMPANIES]->(高血压)      |

### 3. 文档入库新增节点类型

通过「上传文档」功能写入 Neo4j 的节点类型：

| 节点类型 | 标签 | 描述 |
|----------|------|------|
| 来源文档 | `SourceDocument` | 上传文件的元信息（文件名、哈希 ID） |
| 文档切片 | `SourceChunk` | 文档分块原文，与实体节点通过 `[:MENTIONS]` 关联 |
| 医学实体 | （同上表 9 种）| LLM 从文档中抽取，按类型 MERGE 到已有节点 |

问答时系统会同时检索知识图谱和 SourceChunk 原文片段，两路内容一并送入 LLM 生成答案。

### 4.疾病节点属性

每个疾病节点包含以下属性：

- `name`：疾病名称
- `desc`：疾病描述
- `prevent`：预防措施
- `cause`：病因
- `get_prob`：发病概率
- `easy_get`：易患人群
- `get_way`：传播方式
- `cure_lasttime`：治疗时间
- `cured_prob`：治愈概率
- `cost_money`：治疗费用
- `yibao_status`：医保状态

## ⚙️ 配置说明

系统支持通过参数控制 **搜索深度** 与 **计算开销**，在“答案完整性”和“响应速度”之间取得平衡。

### 1. 核心配置参数

|         参数         | 类型 |   默认值   |               说明               |
| :------------------: | :--: | :--------: | :------------------------------: |
|  `enable_multi_hop`  | bool |   `True`   |  是否启用多跳查询（第二跳扩展）  |
| `search_budget_mode` | str  | `Deeper` | 搜索预算模式，控制查询范围和数量 |

### 2. 搜索预算模式对比

系统预设两种搜索预算模式，通过 `search_budget_mode` 控制：

#### ✅ `Deeper` 模式（默认，深度优先）

> - **优点**：覆盖范围广，答案更全面
> - **缺点**：查询次数多，响应较慢，API调用成本高

```python
"Deeper": {
​    "entity_limit": 3,           # 单实体查询最多返回3个节点
​    "relation_limit": 10,        # 关系查询最多10条
​    "top_k_triples": 5,          # 最终保留相似度最高的5个三元组
​    "one_hop_limit": 10,         # 第一跳查询最多10条边
​    "top_k_multi_hop_entities": 5, # 选择相似度最高的5个实体进行第二跳
​    "multi_hop_limit": 3         # 第二跳每个实体最多查3条边
}
```

#### ✅ `Deep` 模式（快速模式）

> - **优点**：查询轻量，响应快，节省 API 调用
> - **缺点**：可能遗漏部分关联信息

```python
"Deep": {
​    "entity_limit": 2,
​    "relation_limit": 8,
​    "one_hop_limit": 8,
​    "top_k_triples": 4,
​    "top_k_multi_hop_entities": 4,
​    "multi_hop_limit": 2
}
```

### 3.性能与资源开销对比表

|    配置组合    | 查询深度 | 响应速度 | api次数 |         适用场景         |
| :------------: | :------: | :------: | :-----: | :----------------------: |
|  `Deep`+ 单跳  |  ⚡ 轻量  |   🚀 快   |   少    | 日常问答、演示、低配设备 |
|  `Deep`+ 多跳  |  🌿 中等  |  🐢 中等  |   中    |        平衡型问答        |
| `Deeper`+ 单跳 |  🌲 深度  |   🐢 慢   |   中    |       深度聚焦分析       |
| `Deeper`+ 多跳 |  🌳 超深  |  🐢🐢 慢   |   多    | 科研、复杂推理、完整答案 |

> ⚠️ **注意**：每次查询都会调用多次 Embedding API（计算相似度）和 1~2 次 Chat API（抽取 + 生成），请合理控制使用频率，避免 API 限流或费用超支。
>
> 2026.3.21更新：新增本地缓存，如成功命中，将直接调用前几次生成的词向量，减少token消耗。

### 4. 其他可选配置

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `MAX_UPLOAD_MB` | `50` | 单次上传文件大小上限（MB） |
| `SESSION_MAX_AGE_HOURS` | `2` | 对话记忆保留时长（超时自动清除） |
| `FILE_MAX_AGE_HOURS` | `24` | uploads/segmented 目录临时文件保留时长 |

## 📬 联系与支持

如有问题或建议，请：

- 提交 [Issue](https://github.com/feiyu1104/DUTMed/issues)
- 或联系我们：[feiyucom@outlook.com](mailto:feiyucom@outlook.com)

## 🙏 致谢

- [Neo4j ](https://neo4j.com/)— 图数据库引擎

- [阿里云通义千问 ](https://tongyi.aliyun.com/qianwen/)— 大语言模型支持

- [SAM ](https://github.com/facebookresearch/segment-anything)— 图像分割基础模型

- [Rich ](https://github.com/Textualize/rich)— 终端美化输出

- [Flask ](https://flask.palletsprojects.com/)— Web 框架

- [ansi2html](https://github.com/pycontribs/ansi2html) — 将 Rich 终端彩色输出转为 HTML

- [pypdf](https://github.com/py-pdf/pypdf) — PDF 文本提取（可选，文档入库时使用）

- 感谢所有**贡献者**！完整名单请见 [CONTRIBUTORS.md](CONTRIBUTORS.md)

  我们也欢迎你加入贡献者行列 🎉


> **免责声明**：本系统生成的医学信息仅供参考，不能替代专业医疗建议、诊断或治疗！请在医生指导下进行决策！





