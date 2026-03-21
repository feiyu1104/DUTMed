import hashlib
import importlib
import json
import os
import re
import time
from datetime import datetime
from typing import Dict, List, Tuple

import requests
from dotenv import load_dotenv
from py2neo import Graph


load_dotenv()


class MedicalDocumentIngestionService:
    ENTITY_TYPES = {
        'Disease', 'Category', 'Symptom', 'Department', 'Treatment',
        'Check', 'Drug', 'Food', 'Recipe', 'Person', 'Organization',
        'Time', 'Location', 'Other'
    }
    RELATION_TYPES = {
        'BELONGS_TO', 'HAS_SYMPTOM', 'TREATED_BY', 'USES_TREATMENT',
        'REQUIRES_CHECK', 'RECOMMENDS_DRUG', 'COMMONLY_USES_DRUG',
        'SHOULD_EAT', 'SHOULD_NOT_EAT', 'RECOMMENDS_RECIPE',
        'ACCOMPANIES', 'OTHER'
    }
    ALLOWED_EXTENSIONS = {'.txt', '.json', '.md', '.csv', '.pdf'}

    def __init__(self):
        self.neo4j_uri = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
        self.neo4j_user = os.getenv('NEO4J_USER', 'neo4j')
        self.neo4j_password = os.getenv('NEO4J_PASSWORD', '123456789')
        self.ali_api_key = os.getenv('ALI_API_KEY')
        self.ali_base_url = os.getenv('ALI_BASE_URL')
        self.ali_model = os.getenv('ALI_MODEL0', 'qwen-plus')
        self.upload_dir = os.path.join('static', 'documents')
        os.makedirs(self.upload_dir, exist_ok=True)

        self.graph = None

    def _get_graph(self) -> Graph:
        if self.graph is None:
            self.graph = Graph(self.neo4j_uri, auth=(self.neo4j_user, self.neo4j_password))
        return self.graph

    def is_allowed_file(self, filename: str) -> bool:
        ext = os.path.splitext(filename.lower())[1]
        return ext in self.ALLOWED_EXTENSIONS

    def save_uploaded_file(self, file_storage) -> str:
        filename = file_storage.filename or ''
        if not self.is_allowed_file(filename):
            raise ValueError('不支持的文件类型，仅支持 txt/json/md/csv/pdf')

        safe_name = f"{int(time.time())}_{re.sub(r'[^a-zA-Z0-9_.-]', '_', filename)}"
        file_path = os.path.join(self.upload_dir, safe_name)
        file_storage.save(file_path)
        return file_path

    def ingest_file(self, file_path: str, original_filename: str = '') -> Dict:
        self._validate_runtime_config()
        text = self._read_file_content(file_path)
        if not text.strip():
            raise ValueError('文件内容为空，无法抽取实体关系')

        doc_id = self._build_doc_id(file_path)
        chunks = self._chunk_text(text, chunk_size=800, overlap=120)
        self._merge_document_node(doc_id, original_filename or os.path.basename(file_path), file_path)

        total_entities = 0
        total_relations = 0
        for idx, chunk_text in enumerate(chunks):
            chunk_id = f"{doc_id}_chunk_{idx + 1}"
            self._merge_chunk_node(doc_id, chunk_id, idx + 1, chunk_text)

            extraction = self._extract_entities_relations(chunk_text)
            entities = extraction.get('entities', [])
            relations = extraction.get('relations', [])

            total_entities += len(entities)
            total_relations += len(relations)

            for entity in entities:
                self._merge_entity(entity, doc_id, chunk_id)

            for relation in relations:
                self._merge_relation(relation, doc_id, chunk_id)

        return {
            'success': True,
            'doc_id': doc_id,
            'file_path': file_path,
            'chunks': len(chunks),
            'entities_extracted': total_entities,
            'relations_extracted': total_relations
        }

    def _validate_runtime_config(self):
        if not self.ali_api_key:
            raise EnvironmentError('请在 .env 中设置 ALI_API_KEY')
        if not self.ali_base_url:
            raise EnvironmentError('请在 .env 中设置 ALI_BASE_URL')

    def _read_file_content(self, file_path: str) -> str:
        ext = os.path.splitext(file_path.lower())[1]
        if ext in {'.txt', '.md', '.csv'}:
            return self._read_text_file(file_path)
        if ext == '.json':
            return self._read_json_file(file_path)
        if ext == '.pdf':
            return self._read_pdf_file(file_path)
        raise ValueError(f'暂不支持文件类型: {ext}')

    def _read_text_file(self, file_path: str) -> str:
        for encoding in ('utf-8', 'gbk', 'utf-16'):
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    return f.read()
            except UnicodeDecodeError:
                continue
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read()

    def _read_json_file(self, file_path: str) -> str:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return self._json_to_text(data)

    def _read_pdf_file(self, file_path: str) -> str:
        try:
            pypdf_module = importlib.import_module('pypdf')
            PdfReader = getattr(pypdf_module, 'PdfReader')
        except ImportError as exc:
            raise ImportError('解析 PDF 需要安装 pypdf: pip install pypdf') from exc

        reader = PdfReader(file_path)
        pages = []
        for page in reader.pages:
            pages.append(page.extract_text() or '')
        return '\n'.join(pages)

    def _json_to_text(self, obj) -> str:
        if isinstance(obj, dict):
            parts = []
            for key, value in obj.items():
                parts.append(f"{key}: {self._json_to_text(value)}")
            return '；'.join(parts)
        if isinstance(obj, list):
            return '；'.join(self._json_to_text(item) for item in obj)
        return str(obj)

    def _chunk_text(self, text: str, chunk_size: int = 800, overlap: int = 120) -> List[str]:
        text = re.sub(r'\s+', ' ', text).strip()
        if len(text) <= chunk_size:
            return [text]

        chunks = []
        start = 0
        while start < len(text):
            end = min(start + chunk_size, len(text))
            chunks.append(text[start:end])
            if end == len(text):
                break
            start = max(0, end - overlap)
        return chunks

    def _build_doc_id(self, file_path: str) -> str:
        with open(file_path, 'rb') as f:
            raw = f.read()
        digest = hashlib.sha256(raw).hexdigest()[:16]
        return f"doc_{digest}"

    def _extract_entities_relations(self, text: str) -> Dict:
        prompt = self._build_extraction_prompt(text)
        content = self._call_llm(prompt, temperature=0.2)
        parsed = self._extract_json_from_content(content)

        entities = [self._normalize_entity(e) for e in parsed.get('entities', [])]
        relations = [self._normalize_relation(r) for r in parsed.get('relations', [])]

        entities = [e for e in entities if e['name']]
        relations = [r for r in relations if r['source'] and r['target']]

        return {'entities': entities, 'relations': relations}

    def _build_extraction_prompt(self, text: str) -> str:
        return f"""
你是医学知识图谱信息抽取助手。请从文本中抽取实体和关系，并仅返回 JSON。

实体类型仅允许：Disease, Category, Symptom, Department, Treatment, Check, Drug, Food, Recipe, Person, Organization, Time, Location, Other
关系类型仅允许：BELONGS_TO, HAS_SYMPTOM, TREATED_BY, USES_TREATMENT, REQUIRES_CHECK, RECOMMENDS_DRUG, COMMONLY_USES_DRUG, SHOULD_EAT, SHOULD_NOT_EAT, RECOMMENDS_RECIPE, ACCOMPANIES, OTHER

返回格式严格为：
{{
  "entities": [{{"name": "实体名称", "type": "实体类型"}}],
  "relations": [{{"source": "源实体", "target": "目标实体", "type": "关系类型"}}]
}}

文本：
{text}
""".strip()

    def _call_llm(self, prompt: str, temperature: float = 0.2) -> str:
        url = f"{self.ali_base_url}/chat/completions"
        headers = {
            'Authorization': f'Bearer {self.ali_api_key}',
            'Content-Type': 'application/json'
        }
        payload = {
            'model': self.ali_model,
            'messages': [{'role': 'user', 'content': prompt}],
            'temperature': temperature
        }

        resp = requests.post(url, headers=headers, json=payload, timeout=60)
        if resp.status_code != 200:
            raise RuntimeError(f'LLM 调用失败: {resp.status_code}, {resp.text}')

        data = resp.json()
        try:
            return data['choices'][0]['message']['content']
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f'LLM 返回格式错误: {data}') from exc

    def _extract_json_from_content(self, content: str) -> Dict:
        cleaned = content.strip()
        if '```json' in cleaned:
            cleaned = cleaned.split('```json', 1)[1].split('```', 1)[0].strip()
        elif '```' in cleaned:
            cleaned = cleaned.split('```', 1)[1].split('```', 1)[0].strip()

        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError:
            # 兜底提取第一个 JSON 对象
            match = re.search(r'\{[\s\S]*\}', cleaned)
            if not match:
                return {'entities': [], 'relations': []}
            try:
                parsed = json.loads(match.group(0))
            except json.JSONDecodeError:
                return {'entities': [], 'relations': []}

        if not isinstance(parsed, dict):
            return {'entities': [], 'relations': []}

        return {
            'entities': parsed.get('entities', []) if isinstance(parsed.get('entities', []), list) else [],
            'relations': parsed.get('relations', []) if isinstance(parsed.get('relations', []), list) else []
        }

    def _normalize_entity(self, entity: Dict) -> Dict:
        name = str(entity.get('name', '')).strip()
        etype = str(entity.get('type', 'Other')).strip()
        if etype not in self.ENTITY_TYPES:
            etype = 'Other'
        return {'name': name, 'type': etype}

    def _normalize_relation(self, relation: Dict) -> Dict:
        source = str(relation.get('source', '')).strip()
        target = str(relation.get('target', '')).strip()
        rtype = str(relation.get('type', 'OTHER')).strip().upper()
        if rtype not in self.RELATION_TYPES:
            rtype = 'OTHER'
        return {'source': source, 'target': target, 'type': rtype}

    def _merge_document_node(self, doc_id: str, filename: str, file_path: str):
        graph = self._get_graph()
        now = datetime.utcnow().isoformat()
        graph.run(
            """
            MERGE (d:SourceDocument {doc_id: $doc_id})
            ON CREATE SET d.created_at = $now
            SET d.filename = $filename,
                d.file_path = $file_path,
                d.updated_at = $now
            """,
            doc_id=doc_id,
            filename=filename,
            file_path=file_path,
            now=now
        )

    def _merge_chunk_node(self, doc_id: str, chunk_id: str, chunk_index: int, content: str):
        graph = self._get_graph()
        now = datetime.utcnow().isoformat()
        graph.run(
            """
            MERGE (c:SourceChunk {chunk_id: $chunk_id})
            ON CREATE SET c.created_at = $now
            SET c.chunk_index = $chunk_index,
                c.content = $content,
                c.updated_at = $now
            WITH c
            MATCH (d:SourceDocument {doc_id: $doc_id})
            MERGE (d)-[:HAS_CHUNK]->(c)
            """,
            chunk_id=chunk_id,
            chunk_index=chunk_index,
            content=content,
            doc_id=doc_id,
            now=now
        )

    def _merge_entity(self, entity: Dict, doc_id: str, chunk_id: str):
        graph = self._get_graph()
        label = entity['type'] if entity['type'] in self.ENTITY_TYPES else 'Other'
        name = entity['name']
        now = datetime.utcnow().isoformat()

        query = f"""
        MERGE (e:{label} {{name: $name}})
        ON CREATE SET e.created_at = $now
        SET e.updated_at = $now,
            e.last_source_doc = $doc_id
        WITH e
        MATCH (c:SourceChunk {{chunk_id: $chunk_id}})
        MERGE (c)-[:MENTIONS]->(e)
        """
        graph.run(query, name=name, now=now, doc_id=doc_id, chunk_id=chunk_id)

    def _merge_relation(self, relation: Dict, doc_id: str, chunk_id: str):
        graph = self._get_graph()
        source_name = relation['source']
        target_name = relation['target']
        rel_type = relation['type'] if relation['type'] in self.RELATION_TYPES else 'OTHER'
        now = datetime.utcnow().isoformat()

        # 实体已由 _merge_entity 按正确 label 入库；直接 MATCH，
        # 若任一端点不存在则整条 Cypher 静默跳过，不创建幽灵 Other 节点。
        rel_query = f"""
        MATCH (s {{name: $source_name}})
        MATCH (t {{name: $target_name}})
        MERGE (s)-[r:{rel_type}]->(t)
        ON CREATE SET r.created_at = $now
        SET r.updated_at = $now,
            r.last_source_doc = $doc_id,
            r.last_chunk_id = $chunk_id
        WITH s, t
        MATCH (c:SourceChunk {{chunk_id: $chunk_id}})
        MERGE (c)-[:SUPPORTS_RELATION {{type: $rel_type}}]->(t)
        """
        graph.run(
            rel_query,
            source_name=source_name,
            target_name=target_name,
            rel_type=rel_type,
            now=now,
            doc_id=doc_id,
            chunk_id=chunk_id
        )


document_ingestion_service = MedicalDocumentIngestionService()
