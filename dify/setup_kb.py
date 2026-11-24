"""把 dify/kb_docs 导入 Dify 知识库（Knowledge Service API）。

python -m dify.setup_kb [--reset]
- 通过控制台创建（或复用）知识库「智备-华为AI认证真题库」与知识库 API Key；
- 创建元数据字段 topic / qtype；
- 用 create-by-text 上传每个文档：自定义分隔符 @@@@，一题一段，高质量索引（bge-m3 向量 + 全文混合检索）；
- 批量给文档写入 topic / qtype 元数据；
- 把 dataset_id 写入 dify/state.json，供 build_dsl / setup_apps 使用。
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from dify.console import Console  # noqa: E402

API = os.getenv("DIFY_API_BASE", "http://localhost/v1").rstrip("/")
DOCS = Path(__file__).parent / "kb_docs"
STATE = Path(__file__).parent / "state.json"
KB_NAME = "智备-华为AI认证真题库"
EMBED_PROVIDER, EMBED_MODEL = "langgenius/ollama/ollama", "bge-m3"
# 混合检索：向量（语义）+ 全文（关键词）加权，无需额外的 Rerank 模型
RETRIEVAL = {"search_method": "hybrid_search", "reranking_enable": False, "reranking_mode": "weighted_score",
             "weights": {"weight_type": "customized",
                         "vector_setting": {"vector_weight": 0.5, "embedding_provider_name": EMBED_PROVIDER,
                                            "embedding_model_name": EMBED_MODEL},
                         "keyword_setting": {"keyword_weight": 0.5}},
             "top_k": 10, "score_threshold_enabled": False, "score_threshold": 0}
KB_DESC = ("华为 ICT 认证（HCIA-AI / HCIP-AI Solution，昇腾 AI 全栈）1710 道真题，每段一道题，含题干、选项、答案与解析。"
           "用于讲解 AI 基础、深度学习、大模型、MindSpore、昇腾处理器、CANN、推理部署等知识点时检索依据。")


def load_state() -> dict:
    return json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}


def save_state(**kw) -> dict:
    st = {**load_state(), **kw}
    STATE.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
    return st


def main() -> None:
    c = Console()
    st = load_state()

    # 1. 知识库（复用同名的）
    existing = [d for d in c.get("/datasets", params={"page": 1, "limit": 100})["data"] if d["name"] == KB_NAME]
    if existing and "--reset" in sys.argv:
        for d in existing:
            c.req("DELETE", f"/datasets/{d['id']}")
        print("deleted old dataset(s)")
        existing = []
    if existing:
        ds_id = existing[0]["id"]
    else:
        ds_id = c.post("/datasets", json={"name": KB_NAME, "description": KB_DESC,
                                          "indexing_technique": "high_quality", "permission": "only_me"})["id"]
    print("dataset:", ds_id)

    # 2. 知识库 API Key
    key = st.get("dataset_api_key")
    if not key:
        key = c.post("/datasets/api-keys")["token"]
    save_state(dataset_id=ds_id, dataset_api_key=key)
    H = {"Authorization": f"Bearer {key}"}

    def api(method, path, **kw):
        r = requests.request(method, f"{API}{path}", headers=H, timeout=120, **kw)
        if not r.ok:
            raise RuntimeError(f"{method} {path} -> {r.status_code}: {r.text[:400]}")
        return r.json() if r.content else {}

    # 3. 元数据字段
    fields = {f["name"]: f["id"] for f in api("GET", f"/datasets/{ds_id}/metadata")["doc_metadata"]}
    for name in ("topic", "qtype"):
        if name not in fields:
            fields[name] = api("POST", f"/datasets/{ds_id}/metadata", json={"type": "string", "name": name})["id"]
    print("metadata fields:", fields)

    # 4. 上传文档（已存在同名文档则跳过）
    have = {d["name"]: d["id"] for d in api("GET", f"/datasets/{ds_id}/documents",
                                            params={"page": 1, "limit": 100})["data"]}
    manifest = json.loads((DOCS / "manifest.json").read_text(encoding="utf-8"))
    process_rule = {"mode": "custom", "rules": {
        "pre_processing_rules": [{"id": "remove_extra_spaces", "enabled": True},
                                 {"id": "remove_urls_emails", "enabled": False}],
        "segmentation": {"separator": "@@@@", "max_tokens": 1200, "chunk_overlap": 0}}}
    doc_ids = {}
    for m in manifest:
        name = m["file"][:-4]
        if name in have:
            doc_ids[name] = have[name]
            continue
        text = (DOCS / m["file"]).read_text(encoding="utf-8")
        r = api("POST", f"/datasets/{ds_id}/document/create-by-text", json={
            "name": name, "text": text, "indexing_technique": "high_quality",
            "embedding_model": EMBED_MODEL, "embedding_model_provider": EMBED_PROVIDER, "retrieval_model": RETRIEVAL,
            "doc_form": "text_model", "doc_language": "Chinese", "process_rule": process_rule})
        doc_ids[name] = r["document"]["id"]
        print(f"  uploaded {name} ({m['count']} 题)")

    # 5. 批量写元数据
    ops = []
    for m in manifest:
        did = doc_ids[m["file"][:-4]]
        ops.append({"document_id": did, "metadata_list": [
            {"id": fields["topic"], "name": "topic", "value": m["topic"]},
            {"id": fields["qtype"], "name": "qtype", "value": m["qtype"]}]})
    api("POST", f"/datasets/{ds_id}/documents/metadata", json={"operation_data": ops})
    print("metadata written for", len(ops), "documents")

    # 知识库默认检索方式（Agent 直接检索知识库时使用）设为混合检索
    c.patch(f"/datasets/{ds_id}", json={"name": KB_NAME, "description": KB_DESC, "permission": "only_me",
                                        "indexing_technique": "high_quality", "embedding_model": EMBED_MODEL,
                                        "embedding_model_provider": EMBED_PROVIDER, "retrieval_model": RETRIEVAL})

    # 6. 等待索引完成
    for _ in range(300):
        docs = api("GET", f"/datasets/{ds_id}/documents", params={"page": 1, "limit": 100})["data"]
        pending = [d["name"] for d in docs if d.get("indexing_status") != "completed"]
        if not pending:
            break
        time.sleep(3)
    total_segments = sum(d.get("segment_count") or 0 for d in docs)
    print(f"indexed: {len(docs)} documents, {total_segments} segments, pending={pending[:5]}")
    save_state(dataset_id=ds_id, segments=total_segments)


if __name__ == "__main__":
    main()
