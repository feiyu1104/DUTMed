# DUTMed 技术实现文档

> 本文档详细描述项目各模块的技术实现原理、数据流与关键设计决策。面向希望深入理解或二次开发本项目的技术读者。

---

## 目录

1. [系统总览](#1-系统总览)
2. [问答核心：RAG 系统（q_a.py）](#2-问答核心rag-系统q_apy)
3. [Web 服务层（app.py）](#3-web-服务层apppy)
4. [文档知识入库（document_ingestion.py）](#4-文档知识入库document_ingestionpy)
5. [图像分割（image_segmentation.py）](#5-图像分割image_segmentationpy)
6. [图像描述与摘要（image_description.py）](#6-图像描述与摘要image_descriptionpy)
7. [前端实现（script.js）](#7-前端实现scriptjs)
8. [并发与线程安全](#8-并发与线程安全)
9. [数据模型：Neo4j 图结构](#9-数据模型neo4j-图结构)
10. [配置参考](#10-配置参考)

---

## 1. 系统总览

DUTMed 是一个多模态医学问答系统，核心架构如下：

```
用户浏览器
  │
  │  HTTP / SSE（Server-Sent Events）
  ▼
Flask Web 服务（app.py）
  │
  ├─► Neo4jRAGSystem（q_a.py）          ← 文本问答主链路
  │     ├─ 多轮对话改写
  │     ├─ 实体关系抽取
  │     ├─ Neo4j 图谱查询
  │     └─ LLM 答案生成
  │
  ├─► 图像处理链路
  │     ├─ ImageSegmentationService      ← FastSAM 分割
  │     └─ ImageDescriptionService       ← Qwen-VL 描述 + 摘要
  │
  └─► MedicalDocumentIngestionService    ← 文档入库
        ├─ 文件解析 / 分块
        ├─ LLM 实体关系抽取
        └─ Neo4j 写入
              │
              ▼
         Neo4j 图数据库
```

### 主要技术栈

| 层次 | 技术 |
|------|------|
| Web 框架 | Flask（threaded 模式） |
| 知识图谱 | Neo4j + py2neo |
| 大语言模型 | 阿里云通义千问（qwen-plus）|
| 视觉模型 | 通义千问 Qwen-VL（qwen-vl-plus）|
| Embedding | text-embedding-v4（阿里云）|
| 图像分割 | FastSAM（Facebook CASIA-IVA-Lab）|
| 流式推送 | Server-Sent Events（SSE）|
| 终端输出 | Rich + ansi2html |

---

## 2. 问答核心：RAG 系统（q_a.py）

### 2.1 整体流程

用户问题进入后，`answer_question()` 按以下 5 步依次处理：

```
问题输入
   │
   ▼ Step 0
多轮对话改写（rewrite_question_with_history）
   │
   ▼ Step 1
实体关系抽取（extract_entities_relations）
   │
   ▼ Step 2
Neo4j 图谱查询（query_neo4j）
   │  ├─ 一跳关系查询
   │  ├─ 多跳推理（可选）
   │  └─ SourceChunk 原文检索
   │
   ▼ Step 3
LLM 答案生成（generate_answer）
   │
   ▼
答案输出（str）
```

---

### 2.2 Step 0：多轮对话改写

**目的**：将含有指代词的模糊问题改写为独立完整的问句，使后续实体提取更准确。

**实现**（`rewrite_question_with_history`）：

```python
def rewrite_question_with_history(self, question: str, history: List[Dict]) -> str:
    if not history:
        return question  # 无历史，直接返回

    # 取最近 6 条消息（3 轮对话）
    history_text = "\n".join(
        f"{'用户' if m['role']=='user' else '助手'}：{m['content'][:300]}"
        for m in history[-6:]
    )
    prompt = (
        f"以下是对话历史：\n{history_text}\n\n当前问题：{question}\n\n"
        "若当前问题含有指代词（它、这个、该病、上述等）或省略了主语，"
        "请结合历史将其改写为独立完整的问题。只输出改写后的问题。"
    )
    rewritten = self.call_llm(prompt, temperature=0.1).strip()
    return rewritten if rewritten else question
```

- **温度 0.1**：尽可能确定性输出，避免改写引入新信息
- **历史截取**：只用最近 6 条，控制 prompt 长度
- **失败降级**：LLM 调用异常时直接返回原始问题，保证流程不中断

---

### 2.3 Step 1：实体关系抽取

**目的**：从问题文本中识别出医学实体（如疾病名、药物名）和实体间关系，作为图谱查询的入口。

**实现**（`extract_entities_relations`）：

1. 构建提示词，列出 14 种实体类型和 12 种关系类型，要求 LLM 输出严格 JSON
2. 调用 `call_llm(prompt, temperature=0.2)`
3. 解析 JSON（兼容 ` ```json ` 代码块包裹）
4. 规范化实体/关系格式，过滤非法类型

**支持的实体类型（14 种）**：

| 标签 | 含义 |
|------|------|
| `Disease` | 疾病 |
| `Symptom` | 症状 |
| `Drug` | 药物 |
| `Treatment` | 治疗方法 |
| `Check` | 检查项目 |
| `Department` | 科室 |
| `Food` | 食物 |
| `Recipe` | 食谱 |
| `Category` | 分类 |
| `Person` | 人物 |
| `Organization` | 机构 |
| `Time` | 时间 |
| `Location` | 地点 |
| `Other` | 其他 |

**支持的关系类型（12 种）**：
`BELONGS_TO`、`HAS_SYMPTOM`、`TREATED_BY`、`USES_TREATMENT`、`REQUIRES_CHECK`、`RECOMMENDS_DRUG`、`COMMONLY_USES_DRUG`、`SHOULD_EAT`、`SHOULD_NOT_EAT`、`RECOMMENDS_RECIPE`、`ACCOMPANIES`、`OTHER`

---

### 2.4 Step 2：Neo4j 图谱查询

`query_neo4j()` 分 5 个子步骤构建 `knowledge` 字典：

```python
result = {
    "entity_properties": [],   # 节点属性
    "related_triples": [],     # 三元组（打分排序）
    "source_chunks": []        # 原文片段
}
```

#### 子步骤 1：节点属性查询

对每个抽取到的实体，直接按 name 在 Neo4j 中匹配：

```cypher
-- Disease 类型
MATCH (n:Disease {name: $name}) RETURN n LIMIT {entity_limit}

-- 其他类型
MATCH (n {name: $name}) RETURN n LIMIT {entity_limit}
```

#### 子步骤 2：关系三元组查询 + Embedding 排序

对抽取到的关系，分别以 source 和 target 为起点查询邻居：

```cypher
MATCH (s)-[r]->(t) WHERE s.name = $source RETURN s, type(r) AS rel, t LIMIT {relation_limit}
MATCH (s)-[r]->(t) WHERE t.name = $target RETURN s, type(r) AS rel, t LIMIT {relation_limit}
```

查到三元组后，将每条三元组转为文本（`"source → rel → target"`），计算与问题 Embedding 的余弦相似度，取相似度最高的 `top_k_triples` 条。

**Embedding 实现**：

- 模型：`text-embedding-v4`（阿里云）
- 接口：`POST {ALI_BASE_URL}/embeddings`
- 载荷：`{"model": "text-embedding-v4", "input": text}`
- 返回：`data['data'][0]['embedding']`（浮点向量）
- 含重试：最多 3 次，指数退避（1s → 2s → 4s），429 限流自动重试

**模块级缓存**：

```python
_embedding_cache: Dict[str, List[float]] = {}
_embedding_cache_lock = threading.Lock()

def get_embedding(self, text: str) -> List[float]:
    if text in _embedding_cache:        # 无锁快速路径
        return _embedding_cache[text]
    # ... API 调用 ...
    with _embedding_cache_lock:         # 写时加锁
        _embedding_cache[text] = vector
    return vector
```

读取不加锁（CPython GIL 保护），写入加锁，避免缓存竞态。

#### 子步骤 3：一跳关系查询

对每个锚点实体，分别查询出向和入向邻居：

```cypher
MATCH (n)-[r]->(m) WHERE n.name = $name RETURN n, type(r) AS rel, m LIMIT {one_hop_limit * 10}
MATCH (n)<-[r]-(m) WHERE n.name = $name RETURN m, type(r) AS rel, n LIMIT {one_hop_limit * 10}
```

> `LIMIT` 使用 `one_hop_limit × 10` 而非 `one_hop_limit`，原因：原始知识图谱数据按插入顺序排列，直接 LIMIT 小值会导致后来通过文档入库新增的关系（如用药关系）被截断而永远不出现。扩大查询范围后再按关系类型分组去重，每类最多保留 5 条。

#### 子步骤 4：多跳推理（可选）

当 `enable_multi_hop=True` 时，从一跳查询结果中按 Embedding 相似度选出 `top_k_multi_hop_entities` 个实体，对每个再做一次一跳查询：

```cypher
MATCH (n)-[r]->(m) WHERE n.name = $name RETURN n, type(r) AS rel, m LIMIT {multi_hop_limit}
```

二跳结果在 `related_triples` 中带 `"hop": 2` 标记，与一跳结果合并后统一排序。

#### 子步骤 5：SourceChunk 原文检索

利用文档入库建立的 `[:MENTIONS]` 边，找出包含本次查询实体的文档原文片段：

```cypher
-- 主查询（MENTIONS 边精确匹配）
MATCH (c:SourceChunk)-[:MENTIONS]->(e)
WHERE e.name IN $names
RETURN c.content AS content, c.chunk_id AS chunk_id, e.name AS entity_name
ORDER BY c.chunk_index
LIMIT 5

-- 兜底查询（CONTAINS 文本包含，应对实体名不完全匹配）
MATCH (c:SourceChunk)
WHERE ANY(name IN $names WHERE c.content CONTAINS name)
RETURN c.content, c.chunk_id,
       [name IN $names WHERE c.content CONTAINS name][0] AS entity_name
ORDER BY c.chunk_index
LIMIT 5
```

---

### 2.5 Step 3：答案生成

`generate_answer()` 将所有检索结果组装进 LLM prompt：

```
系统提示（医学专家角色）
  +
对话历史（最近 6 条消息，每条截取前 300 字）
  +
实体属性（最多 10 个节点的属性字典）
  +
关系三元组（最多 20 条，按相似度排序的 JSON 列表）
  +
原文片段（最多 5 段，每段截取前 400 字，含来源实体标注）
  +
当前问题
```

当 prompt 超过 8000 字符时自动缩减：实体数降至 5，三元组降至 10。

---

### 2.6 搜索预算模式

通过 `search_budget_mode` 控制各步骤的查询量：

| 参数 | Deeper（默认）| Deep |
|------|--------------|------|
| `entity_limit` | 3 | 2 |
| `relation_limit` | 10 | 8 |
| `top_k_triples` | 5 | 4 |
| `one_hop_limit` | 10 | 8 |
| `top_k_multi_hop_entities` | 5 | 4 |
| `multi_hop_limit` | 3 | 2 |

---

### 2.7 LLM 调用实现

所有文本 LLM 调用走同一个方法 `call_llm()`：

- **接口**：`POST {ALI_BASE_URL}/chat/completions`
- **认证**：`Authorization: Bearer {ALI_API_KEY}`
- **载荷**：`{"model": "qwen-plus", "messages": [...], "temperature": float}`
- **重试**：最多 3 次，指数退避（1s、2s、4s），HTTP 429 时自动等待后重试
- **超时**：60 秒

---

## 3. Web 服务层（app.py）

### 3.1 SSE 流式响应

问答接口 `/ask` 采用 **Server-Sent Events** 实现实时流式推送，核心流程：

```
HTTP POST /ask
   │
   ├─ 创建 queue.Queue()（无界队列）
   ├─ 创建 threading.Event()（完成信号）
   │
   ├─ 启动 rag_worker 线程
   │     │
   │     ├─ 调用 rag_system.answer_question()
   │     ├─ 每次 Rich console 输出 → 经 ThreadLocalStream → 转 HTML → put(log_html)
   │     ├─ 完成时 put(answer)
   │     └─ finally: put(finished)
   │
   └─ SSE Generator（主线程）
         │  while not finished or not queue.empty():
         │    msg = queue.get(timeout=0.1)
         └─ yield f"data: {json.dumps(msg)}\n\n"
```

**SSE 事件类型**：

| type | 内容 | 前端处理 |
|------|------|----------|
| `log_html` | Rich 输出转换的 HTML 片段 | 追加到日志面板 |
| `answer` | LLM 最终答案文本 | 显示在对话区 |
| `error` | 错误信息 | 显示错误提示 |
| `finished` | 空 | 停止读取流 |

---

### 3.2 ThreadLocalStream：并发日志隔离

**问题**：多个请求并发时，如果直接修改 `q_a.console.file`，后来的请求会覆盖前一个请求的输出目标，导致日志串流。

**解决方案**：`ThreadLocalStream` 利用 `threading.local()` 为每个线程维护独立的输出流：

```python
class ThreadLocalStream(io.TextIOBase):
    def __init__(self):
        self._local = threading.local()  # 每个线程独立存储

    def set_stream(self, stream):
        self._local.stream = stream      # 注册当前线程的输出目标

    def write(self, s: str):
        stream = getattr(self._local, 'stream', None)
        if stream:
            return stream.write(s)       # 路由到本线程的 SSE 包装器
        return len(s)                    # 无注册则静默丢弃
```

启动时一次性将 `q_a.console.file` 指向全局 `_thread_local_stream`，之后每个 worker 线程只需注册/注销自己的 `SseLogStreamWrapper`：

```python
# 请求处理时
_thread_local_stream.set_stream(worker_sse_wrapper)
try:
    ...
finally:
    _thread_local_stream.clear_stream()  # 保证注销
```

---

### 3.3 RAG 实例缓存

`Neo4jRAGSystem` 初始化成本较高（建立 Neo4j 连接、加载配置），因此使用字典按参数组合缓存：

```python
_rag_instances: Dict[Tuple[bool, str], Neo4jRAGSystem] = {}
_rag_instances_lock = threading.Lock()

def get_rag_system(multi_hop: bool, budget: str):
    key = (multi_hop, budget)
    if key not in _rag_instances:          # 无锁快速检查
        with _rag_instances_lock:
            if key not in _rag_instances:  # 双重检查，防止并发重复创建
                _rag_instances[key] = Neo4jRAGSystem(...)
    return _rag_instances[key]
```

最多创建 4 个实例（`enable_multi_hop` × `search_budget_mode` 的组合数）。

---

### 3.4 多轮对话记忆存储

会话历史存储在内存字典中，以 `session_id` 为键：

```python
_conversation_history: Dict[str, {
    "messages": List[{"role": str, "content": str}],
    "last_active": float
}] = {}
```

- **session_id** 由前端在 `sessionStorage` 中生成并维护，格式：`sess_{timestamp}_{random}`，同一浏览器标签页共享同一 session
- 每轮对话追加 user + assistant 两条消息，超过 20 条时裁剪为最新的 20 条（10 轮）
- 历史作为参数传入 `answer_question(history=history)`，在 Step 0 改写问题、Step 3 生成答案时均注入

---

### 3.5 文件清理守护线程

启动时创建 daemon 线程，定期删除过期临时文件和过期会话：

```python
def _cleanup_old_files():
    now = time.time()
    # 删除 static/uploads/ 和 static/segmented/ 中超期文件
    for directory in _CLEANUP_DIRS:
        for filename in os.listdir(directory):
            age = now - os.path.getmtime(filepath)
            if age > _FILE_MAX_AGE_SECONDS:
                os.remove(filepath)

    # 删除超期 session
    with _history_lock:
        expired = [sid for sid, e in _conversation_history.items()
                   if now - e["last_active"] > _SESSION_MAX_AGE_SECONDS]
        for sid in expired:
            del _conversation_history[sid]
```

- 扫描间隔：1 小时
- 文件默认保留：24 小时（`FILE_MAX_AGE_HOURS`）
- Session 默认保留：2 小时（`SESSION_MAX_AGE_HOURS`）

---

### 3.6 文件上传安全

通过 Flask 的 `MAX_CONTENT_LENGTH` 限制单次请求大小：

```python
app.config['MAX_CONTENT_LENGTH'] = int(os.getenv('MAX_UPLOAD_MB', '50')) * 1024 * 1024
```

超限时 Flask 自动返回 413 状态，配合注册的错误处理器返回 JSON：

```python
@app.errorhandler(413)
def request_entity_too_large(e):
    limit_mb = app.config['MAX_CONTENT_LENGTH'] // (1024 * 1024)
    return jsonify({"error": f"文件过大，上传限制为 {limit_mb} MB。"}), 413
```

前端在 fetch 响应后检查 `response.status === 413` 并显示友好提示。

---

## 4. 文档知识入库（document_ingestion.py）

### 4.1 完整流程

```
上传文件
   │
   ├─ 文件类型校验（ALLOWED_EXTENSIONS）
   ├─ 安全文件名生成（时间戳前缀 + 特殊字符过滤）
   │
   ▼
文件内容读取
   ├─ .txt/.md/.csv → 多编码尝试（utf-8 → gbk → utf-16 → 忽略错误）
   ├─ .json         → json.load() → 递归转文本
   └─ .pdf          → pypdf.PdfReader() → 逐页提取文本
   │
   ▼
文档 ID 生成
   └─ SHA-256(文件二进制) → 取前 16 位十六进制 → "doc_{hex}"
   │
   ▼
文本分块（chunk_size=800, overlap=120）
   │
   ├─ MERGE SourceDocument 节点（幂等）
   ├─ MERGE SourceChunk 节点 × N
   │
   └─ for each chunk:
         │
         ├─ LLM 抽取实体关系（temperature=0.2）
         │
         ├─ MERGE 实体节点（按正确 label）
         │    └─ MERGE SourceChunk-[:MENTIONS]->实体
         │
         └─ MATCH 源实体 + 目标实体
              └─ MERGE 关系边（任一端点不存在则静默跳过）
```

### 4.2 文本分块算法

采用固定大小滑动窗口，带重叠保留上下文：

```python
def _chunk_text(self, text, chunk_size=800, overlap=120):
    text = re.sub(r'\s+', ' ', text).strip()  # 合并空白
    if len(text) <= chunk_size:
        return [text]
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append(text[start:end])
        if end == len(text):
            break
        start = max(0, end - overlap)   # 回退 120 字，保留块间上下文
    return chunks
```

- `chunk_size=800`：平衡 LLM 上下文长度与抽取精度
- `overlap=120`：避免跨块的实体/关系被截断

### 4.3 实体关系抽取 Prompt

Prompt 要求 LLM 输出以下严格 JSON 格式：

```json
{
  "entities": [{"name": "实体名称", "type": "实体类型"}],
  "relations": [{"source": "源实体", "target": "目标实体", "type": "关系类型"}]
}
```

解析时兼容 LLM 输出的 ` ```json ` 代码块，使用正则兜底提取首个 JSON 对象。

### 4.4 Neo4j 写入策略

所有写操作均使用 `MERGE` 而非 `CREATE`，保证幂等性（同一文档多次上传不会产生重复节点）：

**关系写入的幽灵节点问题**：早期实现中，若源实体或目标实体在图谱中不存在，会先 `MERGE (s:Other)` 创建幽灵节点，污染图谱。现改为直接 `MATCH`，任一端点不存在时整条 Cypher 静默跳过：

```cypher
MATCH (s {name: $source_name})   -- 任一端点不存在则后续全部跳过
MATCH (t {name: $target_name})
MERGE (s)-[r:RelType]->(t)
...
```

---

## 5. 图像分割（image_segmentation.py）

### 5.1 模型：FastSAM

FastSAM（Fast Segment Anything Model）是 Facebook SAM 的轻量化实现，基于 YOLOv8 架构，支持在单张图像上生成所有物体的分割掩码（Everything 模式）或按提示词/点/框分割特定区域。

权重文件：`./weights/FastSAM_X.pt`（X 为大模型版本，精度更高）

设备选择：

```python
device = torch.device(
    "cuda" if torch.cuda.is_available() else
    "mps"  if torch.backends.mps.is_available() else
    "cpu"
)
```

### 5.2 分割流程

```
原始图像
   │
   ▼
尺寸预处理
   └─ scale = input_size(1024) / max(w, h)
      保持长宽比缩放，长边对齐 1024px
   │
   ▼
FastSAM 推理
   └─ model(image, retina_masks=True, iou=0.7, conf=0.25, imgsz=1024)
   │
   ▼
提示词处理（FastSAMPrompt）
   ├─ 文本提示  → prompt_process.text_prompt(text)
   ├─ 点提示    → prompt_process.point_prompt(points, labels)
   ├─ 框提示    → prompt_process.box_prompt(bboxes)
   └─ 无提示    → prompt_process.everything_prompt()  ← 默认
   │
   ▼
可视化渲染（plot_to_result）
   ├─ mask_random_color=True   每个掩码随机颜色
   ├─ better_quality=True      后处理平滑边缘
   ├─ withContours=True        绘制轮廓线
   └─ retina=True              使用高分辨率掩码
   │
   ▼
保存为 PNG（static/segmented/{uuid}.png）
返回 (segmented_path, original_path, segmentation_info)
```

### 5.3 关键参数说明

| 参数 | 默认值 | 含义 |
|------|--------|------|
| `input_size` | 1024 | 推理时图像长边像素数 |
| `iou_threshold` | 0.7 | NMS 中两个掩码的 IoU 阈值，越高保留的掩码越少 |
| `conf_threshold` | 0.25 | 掩码置信度阈值，越低检测越灵敏 |
| `better_quality` | True | 使用形态学操作平滑掩码边缘 |
| `withContours` | True | 在掩码边缘绘制轮廓线 |
| `use_retina` | True | 以原始分辨率输出掩码（而非降采样） |
| `mask_random_color` | True | 每个分割区域随机着色 |

---

## 6. 图像描述与摘要（image_description.py）

### 6.1 图像描述：Qwen-VL

使用通义千问多模态模型（`qwen-vl-plus`）对分割后图像进行医学专业描述。

**图像编码**：

```python
with open(image_path, "rb") as f:
    b_image = f.read()
image_b64 = base64.b64encode(b_image).decode('utf-8')
```

**多模态消息格式**（OpenAI 兼容）：

```json
{
  "role": "user",
  "content": [
    {
      "type": "image_url",
      "image_url": {"url": "data:image/jpeg;base64,{base64数据}"}
    },
    {
      "type": "text",
      "text": "请作为一名专业的医学影像专家，分析这张经过图像分割处理的医学影像..."
    }
  ]
}
```

**医学影像描述 Prompt** 要求模型从 5 个维度分析：
1. 影像类型识别（X光/CT/MRI/超声/病理切片等）
2. 分割结果分析（分割区域对应的解剖结构）
3. 医学结构识别（器官、组织等）
4. 异常发现（病变、异常表现）
5. 临床意义（潜在诊断参考）

调用参数：`temperature=0.3`（适度降温保证专业性，同时保留一定灵活性）

### 6.2 描述摘要

Qwen-VL 的描述往往包含详细的分点说明，直接用于 RAG 实体提取时噪声较多。因此新增摘要步骤，使用纯文本模型（`qwen-plus`）将描述压缩为 100 字以内的结构化摘要：

```
Prompt 要求提炼：
  - 影像类型
  - 主要解剖结构
  - 关键异常发现（如有）
  - 可能涉及的疾病名称
```

调用参数：`temperature=0.1`（接近确定性输出，确保摘要稳定）

**降级策略**：摘要失败时（网络超时、模型拒答等），退回使用完整描述，不阻断主流程。

### 6.3 图像分析完整链路

```
用户上传图像
   │
   ▼ image_segmentation_service
FastSAM 分割 → 生成彩色掩码图像
   │
   ▼ image_description_service.describe_medical_image()
Qwen-VL 描述分割后图像 → 详细医学分析文本
   │
   ▼ image_description_service.summarize_medical_description()
qwen-plus 摘要 → 100字以内结构化摘要
   │
   ▼ 前端
显示原图 + 分割图 + 完整描述 + 摘要（标注）
   │
   ▼ 自动触发 performQuestion()
以摘要为输入，查询知识图谱，关联相关疾病信息
```

---

## 7. 前端实现（script.js）

### 7.1 SSE 流处理

前端通过 `fetch` + `ReadableStream` 读取 SSE 响应，手动解析数据帧：

```javascript
const reader = response.body.getReader();
const decoder = new TextDecoder();

function processStream() {
    reader.read().then(({ done, value }) => {
        if (done) return;
        const chunk = decoder.decode(value, { stream: true });
        chunk.split('\n\n').forEach(message => {
            if (message.startsWith('data: ')) {
                const jsonData = JSON.parse(message.substring(5).trim());
                // 按 type 分发处理
            }
        });
        processStream(); // 递归读取下一帧
    });
}
```

选择 `fetch` + 手动解析而非 `EventSource` 是因为 `EventSource` 不支持 POST 请求，而问答接口需要传递 JSON body。

### 7.2 会话 ID 管理

```javascript
let sessionId = sessionStorage.getItem('dutmed_session_id');
if (!sessionId) {
    sessionId = 'sess_' + Date.now().toString(36) + '_' + Math.random().toString(36).slice(2, 8);
    sessionStorage.setItem('dutmed_session_id', sessionId);
}
```

使用 `sessionStorage`（而非 `localStorage`）确保：
- 同一标签页内会话连续
- 新标签页/隐私窗口自动开启新会话
- 刷新页面保留会话

点击"清除记忆"时，向服务端发送 `/clear_history`，同时在前端生成新的 `sessionId` 覆盖 `sessionStorage`。

### 7.3 Markdown 轻量渲染

答案文本通过正则替换实现基础 Markdown：

```javascript
let formatted = message
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')  // 粗体
    .replace(/\*(.*?)\*/g,     '<em>$1</em>')           // 斜体
    .replace(/`(.*?)`/g,       '<code>$1</code>')        // 行内代码
    .replace(/\n/g,            '<br>');                  // 换行
```

---

## 8. 并发与线程安全

### 8.1 并发资源汇总

| 资源 | 保护机制 |
|------|----------|
| `_embedding_cache` | `_embedding_cache_lock`（写时加锁，读不加锁） |
| `_rag_instances` | `_rag_instances_lock`（双重检查锁） |
| `_conversation_history` | `_history_lock`（读写均加锁） |
| `q_a.console.file` | `ThreadLocalStream` + `threading.local()` |
| 文件清理 | 独立 daemon 线程，读目录不加锁（可接受轻微竞态） |

### 8.2 线程模型全景

```
主线程（Flask）
   │
   ├─ 请求 A → worker_thread_A
   │              ├─ ThreadLocalStream 注册 SSE_A
   │              ├─ 调用 RAG（共享 Neo4j 连接）
   │              ├─ 产生日志 → SSE_A → queue_A → response_A
   │              └─ 完成后 ThreadLocalStream 注销
   │
   ├─ 请求 B → worker_thread_B
   │              ├─ ThreadLocalStream 注册 SSE_B（独立于 A）
   │              └─ ...
   │
   └─ cleanup_thread（daemon）
              ├─ 每小时扫描临时文件
              └─ 清除过期 session
```

---

## 9. 数据模型：Neo4j 图结构

### 9.1 节点类型

#### 原始知识图谱节点（来自 neo4j_import.py）

| 标签 | 关键属性 |
|------|----------|
| `Disease` | `name`, `desc`, `cause`, `prevent`, `get_prob`, `easy_get`, `cure_lasttime`, `cured_prob`, `cost_money`, `yibao_status` |
| `Symptom` | `name` |
| `Drug` | `name` |
| `Treatment` | `name` |
| `Check` | `name` |
| `Department` | `name` |
| `Food` | `name` |
| `Recipe` | `name` |
| `Category` | `name` |

#### 文档入库新增节点

| 标签 | 关键属性 |
|------|----------|
| `SourceDocument` | `doc_id`, `filename`, `file_path`, `created_at`, `updated_at` |
| `SourceChunk` | `chunk_id`, `chunk_index`, `content`, `created_at`, `updated_at` |

### 9.2 关系类型

#### 医学知识关系

| 关系 | 含义 | 示例 |
|------|------|------|
| `BELONGS_TO` | 疾病属于某分类 | `(肺炎)-[:BELONGS_TO]->(呼吸内科)` |
| `HAS_SYMPTOM` | 疾病有某症状 | `(肺炎)-[:HAS_SYMPTOM]->(发热)` |
| `TREATED_BY` | 由某科室治疗 | `(肺炎)-[:TREATED_BY]->(呼吸内科)` |
| `USES_TREATMENT` | 使用某治疗方法 | `(肺炎)-[:USES_TREATMENT]->(药物治疗)` |
| `REQUIRES_CHECK` | 需要某检查 | `(肺炎)-[:REQUIRES_CHECK]->(胸部CT)` |
| `RECOMMENDS_DRUG` | 推荐某药物 | `(肺炎)-[:RECOMMENDS_DRUG]->(阿奇霉素)` |
| `COMMONLY_USES_DRUG` | 常用某药物 | `(肺炎)-[:COMMONLY_USES_DRUG]->(青霉素)` |
| `SHOULD_EAT` | 宜吃某食物 | `(肺炎)-[:SHOULD_EAT]->(鸡蛋)` |
| `SHOULD_NOT_EAT` | 不宜吃某食物 | `(肺炎)-[:SHOULD_NOT_EAT]->(辣椒)` |
| `RECOMMENDS_RECIPE` | 推荐某食谱 | `(肺炎)-[:RECOMMENDS_RECIPE]->(百合粥)` |
| `ACCOMPANIES` | 伴随疾病 | `(糖尿病)-[:ACCOMPANIES]->(高血压)` |

#### 文档溯源关系

| 关系 | 含义 |
|------|------|
| `HAS_CHUNK` | `SourceDocument → SourceChunk` |
| `MENTIONS` | `SourceChunk → 医学实体` |
| `SUPPORTS_RELATION` | `SourceChunk → 关系目标实体`（带 `type` 属性） |

### 9.3 数据流向图

```
用户上传文档
      │
      ▼
SourceDocument ──HAS_CHUNK──► SourceChunk ──MENTIONS──► Disease/Drug/...
                                   │
                                   └──SUPPORTS_RELATION──► 关系目标实体

问答时：
问题实体
   │
   ├─ MATCH 图谱节点（Disease, Drug 等）
   │     └─ 一跳/多跳关系三元组
   │
   └─ MATCH SourceChunk WHERE MENTIONS 指向问题实体
         └─ 返回原文片段 → 注入 LLM prompt
```

---

## 10. 配置参考

### 环境变量（.env）

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `NEO4J_URI` | `bolt://localhost:7687` | Neo4j 连接地址 |
| `NEO4J_USER` | `neo4j` | Neo4j 用户名 |
| `NEO4J_PASSWORD` | `123456789` | Neo4j 密码 |
| `ALI_API_KEY` | — | 阿里云 API Key（必填）|
| `ALI_BASE_URL` | — | 阿里云 API 基础 URL（必填）|
| `ALI_MODEL0` | `qwen-plus` | 文本模型（问答/抽取/摘要）|
| `ALI_MODEL1` | `qwen-vl-plus` | 视觉模型（图像描述）|
| `MAX_UPLOAD_MB` | `50` | 文件上传大小限制（MB）|
| `SESSION_MAX_AGE_HOURS` | `2` | 对话记忆保留时长（小时）|
| `FILE_MAX_AGE_HOURS` | `24` | 临时文件保留时长（小时）|

### 代码内硬编码参数（可按需修改）

| 位置 | 参数 | 默认值 | 含义 |
|------|------|--------|------|
| `app.py` | `_SESSION_MAX_TURNS` | 20 | 每个 session 最多保留消息条数 |
| `app.py` | `_CLEANUP_INTERVAL_SECONDS` | 3600 | 清理线程扫描间隔（秒）|
| `document_ingestion.py` | `chunk_size` | 800 | 文档分块大小（字符数）|
| `document_ingestion.py` | `overlap` | 120 | 分块重叠大小（字符数）|
| `q_a.py` | `BUDGET_MODES["Deeper"]` | 见§2.6 | Deeper 模式各查询上限 |
| `q_a.py` | `BUDGET_MODES["Deep"]` | 见§2.6 | Deep 模式各查询上限 |
| `image_segmentation.py` | `input_size` | 1024 | 推理图像长边像素 |
| `image_segmentation.py` | `iou_threshold` | 0.7 | FastSAM IoU 阈值 |
| `image_segmentation.py` | `conf_threshold` | 0.25 | FastSAM 置信度阈值 |

---

> **免责声明**：本系统输出的医学信息仅供学术研究和辅助参考，不能替代专业医疗诊断或治疗建议。
