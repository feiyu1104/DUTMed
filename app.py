import os
import json
import io
import time
import threading
import queue  # For thread-safe communication
from flask import Flask, render_template, request, Response, stream_with_context, jsonify, send_from_directory
import q_a  # Assuming q_a.py is in the same directory or accessible via PYTHONPATH
from rich.console import Console
from ansi2html import Ansi2HTMLConverter  # For converting rich's ANSI output to HTML
from py2neo import Graph as Py2neoGraph  # Explicit import for clarity
from image_segmentation import image_segmentation_service  # Import image segmentation service
from image_description import image_description_service  # Import image description service
from document_ingestion import document_ingestion_service  # Import document ingestion service
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# --- Flask App Setup ---
app = Flask(__name__)
app.secret_key = os.urandom(24)  # Still needed for flashing messages, etc.
# 限制上传文件大小：图片最大 20 MB，文档最大 50 MB，取较大值作为统一上限
# 可通过环境变量 MAX_UPLOAD_MB 调整（单位：MB）
app.config['MAX_CONTENT_LENGTH'] = int(os.getenv('MAX_UPLOAD_MB', '50')) * 1024 * 1024

# --- RAG System Instance Cache ---
# Key: (enable_multi_hop: bool, search_budget_mode: str) — at most 4 combinations
_rag_instances: dict = {}
_rag_instances_lock = threading.Lock()

# --- Conversation History Storage ---
# Key: session_id (str) → list of {"role": "user"/"assistant", "content": str, "ts": float}
_conversation_history: dict = {}
_history_lock = threading.Lock()
_SESSION_MAX_AGE_SECONDS = int(os.getenv("SESSION_MAX_AGE_HOURS", "2")) * 3600
_SESSION_MAX_TURNS = 20  # max messages to keep per session (10 rounds)


def get_history(session_id: str) -> list:
    """Return a copy of the message list for the given session."""
    with _history_lock:
        entry = _conversation_history.get(session_id)
        if entry is None:
            return []
        return list(entry["messages"])


def update_history(session_id: str, user_msg: str, assistant_msg: str):
    """Append a user/assistant turn to the session history."""
    with _history_lock:
        if session_id not in _conversation_history:
            _conversation_history[session_id] = {"messages": [], "last_active": time.time()}
        entry = _conversation_history[session_id]
        entry["messages"].append({"role": "user", "content": user_msg})
        entry["messages"].append({"role": "assistant", "content": assistant_msg})
        # Keep only the most recent turns
        if len(entry["messages"]) > _SESSION_MAX_TURNS:
            entry["messages"] = entry["messages"][-_SESSION_MAX_TURNS:]
        entry["last_active"] = time.time()


def clear_history(session_id: str):
    """Remove session history (e.g., user clicked 清除记忆)."""
    with _history_lock:
        _conversation_history.pop(session_id, None)


def get_rag_system(multi_hop: bool, budget: str):
    """Return a cached Neo4jRAGSystem for the given parameter combination."""
    key = (multi_hop, budget)
    if key not in _rag_instances:
        with _rag_instances_lock:
            if key not in _rag_instances:
                _rag_instances[key] = q_a.Neo4jRAGSystem(
                    neo4j_uri=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
                    neo4j_user=os.getenv("NEO4J_USER", "neo4j"),
                    neo4j_password=os.getenv("NEO4J_PASSWORD", "123456789"),
                    enable_multi_hop=multi_hop,
                    search_budget_mode=budget,
                )
    return _rag_instances[key]


# --- 线程安全的日志流 ---
class ThreadLocalStream(io.TextIOBase):
    """
    将 write() 调用分发到各请求线程自己注册的流。
    q_a.console.file 启动时设为此对象（一次性），
    每个 worker 线程通过 set_stream / clear_stream 注册/注销自己的 SSE 包装器，
    彻底消除多并发请求互相覆盖 console.file 的竞态条件。
    """
    def __init__(self):
        self._local = threading.local()

    def set_stream(self, stream):
        self._local.stream = stream

    def clear_stream(self):
        try:
            del self._local.stream
        except AttributeError:
            pass

    def _get_stream(self):
        return getattr(self._local, 'stream', None)

    def write(self, s: str):
        stream = self._get_stream()
        if stream:
            return stream.write(s)
        return len(s) if isinstance(s, str) else 0

    def flush(self):
        stream = self._get_stream()
        if stream:
            stream.flush()

    def isatty(self): return False
    def readable(self): return False
    def seekable(self): return False
    def writable(self): return True


_thread_local_stream = ThreadLocalStream()
# 启动时将全局 console 的输出重定向到线程局部流（一次性，永不再改）
if hasattr(q_a, 'console'):
    q_a.console.file = _thread_local_stream


# --- Routes ---
@app.route("/", methods=["GET"])
def index():
    # ✅ 从环境变量获取 Neo4j 配置，传给前端显示
    neo4j_config = {
        "uri": os.getenv("NEO4J_URI"),
        "user": os.getenv("NEO4J_USER"),
    }
    return render_template("index.html", neo4j_config=neo4j_config)


@app.route("/clear_history", methods=["POST"])
def clear_history_route():
    data = request.json or {}
    session_id = data.get("session_id", "").strip()
    if session_id:
        clear_history(session_id)
    return jsonify({"success": True})


@app.route("/ask", methods=["POST"])
def ask_question():
    data = request.json
    question_text = data.get("question")
    enable_multi_hop = data.get("enable_multi_hop", True)
    search_budget = data.get("search_budget", "Deeper")
    session_id = data.get("session_id", "").strip()

    if not question_text:
        return Response(json.dumps({"error": "No question provided."}), status=400, mimetype='application/json')

    history = get_history(session_id) if session_id else []

    def generate_response_stream():
        message_queue = queue.Queue()
        finished_signal = threading.Event()

        class SseLogStreamWrapper(io.TextIOBase):
            def __init__(self, q):
                self.queue = q
                self.buffer = ""
                self.ansi_conv = Ansi2HTMLConverter(inline=True, scheme="solarized", linkify=False, dark_bg=True)

            def write(self, s: str):
                if not isinstance(s, str):
                    try:
                        s = s.decode(errors='replace')
                    except (AttributeError, UnicodeDecodeError):
                        s = str(s)
                self.buffer += s
                while True:
                    try:
                        newline_index = self.buffer.index('\n')
                    except ValueError:
                        break
                    line_to_process = self.buffer[:newline_index + 1]
                    self.buffer = self.buffer[newline_index + 1:]
                    if line_to_process.strip():
                        html_line = self.ansi_conv.convert(line_to_process.strip(), full=False)
                        self.queue.put({'type': 'log_html', 'content': f"<div class='log-item'>{html_line}</div>"})
                return len(s.encode())

            def flush(self):
                if self.buffer.strip():
                    html_line = self.ansi_conv.convert(self.buffer.strip(), full=False)
                    self.queue.put({'type': 'log_html', 'content': f"<div class='log-item'>{html_line}</div>"})
                    self.buffer = ""

            def isatty(self): return False
            def readable(self): return False
            def seekable(self): return False
            def writable(self): return True

        def rag_worker(q, question, multi_hop, budget, finish_event, conv_history, sess_id):
            worker_sse_wrapper = SseLogStreamWrapper(q)
            # 将本线程的日志输出注册到线程局部流，与其他并发请求完全隔离
            _thread_local_stream.set_stream(worker_sse_wrapper)
            try:
                rag_system = get_rag_system(multi_hop, budget)
                final_answer = rag_system.answer_question(question, history=conv_history)
                worker_sse_wrapper.flush()
                # 将本轮对话写回历史
                if sess_id:
                    update_history(sess_id, question, final_answer)
                q.put({'type': 'answer', 'content': final_answer})

            except Exception as e:
                app.logger.error(f"Error in RAG worker thread: {e}", exc_info=True)
                try:
                    worker_sse_wrapper.flush()
                except:
                    pass
                q.put({'type': 'error', 'content': f"An error occurred: {str(e)}"})
            finally:
                _thread_local_stream.clear_stream()
                finish_event.set()
                q.put({'type': 'finished'})

        worker_thread = threading.Thread(target=rag_worker, args=(
            message_queue, question_text, enable_multi_hop, search_budget,
            finished_signal, history, session_id))
        worker_thread.start()

        while not finished_signal.is_set() or not message_queue.empty():
            try:
                msg = message_queue.get(timeout=0.1)
                yield f"data: {json.dumps(msg)}\n\n"
                if msg.get('type') == 'finished':
                    break
            except queue.Empty:
                continue
            except Exception as e:
                app.logger.error(f"Error yielding SSE message: {e}")
                break

    return Response(stream_with_context(generate_response_stream()), mimetype='text/event-stream')


@app.route('/upload_image', methods=['POST'])
def upload_image():
    """处理图像文件上传和分割"""
    if 'image' not in request.files:
        return jsonify({"error": "No image file uploaded."}), 400

    image_file = request.files['image']
    if image_file.filename == '':
        return jsonify({"error": "No image file selected."}), 400

    allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'tiff'}
    if not (image_file.filename and '.' in image_file.filename and
            image_file.filename.rsplit('.', 1)[1].lower() in allowed_extensions):
        return jsonify({"error": "Unsupported file type. Please upload PNG, JPG, JPEG, GIF, BMP, or TIFF files."}), 400

    try:
        app.logger.info(f"开始处理图像文件: {image_file.filename}")
        uploaded_path = image_segmentation_service.save_uploaded_image(image_file)

        if not uploaded_path:
            return jsonify({"error": "Failed to save uploaded image."}), 500

        app.logger.info(f"开始图像分割: {uploaded_path}")
        segmented_path, original_path, seg_info = image_segmentation_service.segment_image(
            uploaded_path,
            input_size=1024,
            iou_threshold=0.7,
            conf_threshold=0.25,
            better_quality=True,
            withContours=True,
            use_retina=True,
            mask_random_color=True
        )

        if not segmented_path:
            app.logger.error(f"图像分割失败: {seg_info}")
            return jsonify({"error": f"Image segmentation failed: {seg_info}"}), 500

        app.logger.info(f"开始图像描述: {segmented_path}")
        success, description = image_description_service.describe_medical_image(segmented_path)

        if not success:
            app.logger.warning(f"图像描述失败: {description}")
            description = "图像描述生成失败，但图像分割已完成。"

        # 对描述进行摘要，用于后续 RAG 查询
        summary = description  # 默认退回原文
        if success and description:
            sum_ok, sum_text = image_description_service.summarize_medical_description(description)
            if sum_ok and sum_text:
                summary = sum_text
                app.logger.info(f"影像描述摘要完成: {summary[:80]}...")
            else:
                app.logger.warning(f"摘要生成失败，使用原始描述: {sum_text}")

        app.logger.info(f"图像分割和描述完成: {segmented_path}")
        return jsonify({
            "success": True,
            "original_image": f"/uploads/{os.path.basename(original_path)}",
            "segmented_image": f"/segmented/{os.path.basename(segmented_path)}",
            "segmentation_info": seg_info,
            "description": description,
            "summary": summary
        })

    except Exception as e:
        app.logger.error(f"图像分割过程中出错: {e}", exc_info=True)
        return jsonify({"error": f"Image segmentation error: {str(e)}"}), 500


@app.route('/upload_document', methods=['POST'])
def upload_document():
    """处理文档上传并自动抽取实体关系入库"""
    if 'document' not in request.files:
        return jsonify({"error": "No document file uploaded."}), 400

    document_file = request.files['document']
    if document_file.filename == '':
        return jsonify({"error": "No document file selected."}), 400

    if not document_ingestion_service.is_allowed_file(document_file.filename):
        return jsonify({"error": "Unsupported file type. Please upload TXT, JSON, MD, CSV, or PDF files."}), 400

    try:
        app.logger.info(f"开始处理文档文件: {document_file.filename}")
        saved_path = document_ingestion_service.save_uploaded_file(document_file)
        ingest_result = document_ingestion_service.ingest_file(saved_path, document_file.filename)
        app.logger.info(f"文档入库完成: {ingest_result}")

        return jsonify({
            "success": True,
            "message": "Document ingested successfully.",
            "result": ingest_result
        })
    except Exception as e:
        app.logger.error(f"文档入库过程中出错: {e}", exc_info=True)
        return jsonify({"error": f"Document ingestion error: {str(e)}"}), 500


@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory('static/uploads', filename)


@app.route('/segmented/<filename>')
def segmented_file(filename):
    return send_from_directory('static/segmented', filename)


@app.errorhandler(413)
def request_entity_too_large(e):
    limit_mb = app.config['MAX_CONTENT_LENGTH'] // (1024 * 1024)
    return jsonify({"error": f"文件过大，上传限制为 {limit_mb} MB。"}), 413


# --- Startup Neo4j Connection Test ---
def test_neo4j_connection():
    try:
        graph = Py2neoGraph(
            os.getenv("NEO4J_URI", "bolt://localhost:7687"),
            auth=(
                os.getenv("NEO4J_USER", "neo4j"),
                os.getenv("NEO4J_PASSWORD", "123456789")
            )
        )
        graph.run("RETURN 1")
        app.logger.info("Neo4j connection successful at startup.")
    except Exception as e:
        app.logger.error(f"Neo4j connection failed at startup: {e}")


# --- 临时文件清理 ---
# 图像上传/分割产生的文件无需永久保留，超过保留期后自动删除。
# documents/ 目录存放已入库的文档，有持久价值，不纳入清理范围。
_CLEANUP_DIRS = [
    os.path.join("static", "uploads"),
    os.path.join("static", "segmented"),
]
_FILE_MAX_AGE_SECONDS = int(os.getenv("FILE_MAX_AGE_HOURS", "24")) * 3600
_CLEANUP_INTERVAL_SECONDS = 3600  # 每小时扫描一次


def _cleanup_old_files():
    """删除 uploads/ 和 segmented/ 中超过保留期的文件；清理过期 session 历史。"""
    import time as _time
    now = _time.time()
    total = 0
    for directory in _CLEANUP_DIRS:
        if not os.path.isdir(directory):
            continue
        for filename in os.listdir(directory):
            filepath = os.path.join(directory, filename)
            if not os.path.isfile(filepath):
                continue
            try:
                age = now - os.path.getmtime(filepath)
                if age > _FILE_MAX_AGE_SECONDS:
                    os.remove(filepath)
                    total += 1
            except OSError:
                pass
    if total:
        app.logger.info(f"文件清理：已删除 {total} 个过期临时文件。")

    # 清理过期 session 历史
    expired_sessions = []
    with _history_lock:
        for sid, entry in _conversation_history.items():
            if now - entry["last_active"] > _SESSION_MAX_AGE_SECONDS:
                expired_sessions.append(sid)
        for sid in expired_sessions:
            del _conversation_history[sid]
    if expired_sessions:
        app.logger.info(f"会话清理：已清除 {len(expired_sessions)} 个过期会话历史。")


def _cleanup_worker():
    """后台守护线程：启动时立即清理一次，此后每隔 1 小时再次清理。"""
    import time as _time
    _cleanup_old_files()
    while True:
        _time.sleep(_CLEANUP_INTERVAL_SECONDS)
        _cleanup_old_files()


def _start_cleanup_thread():
    t = threading.Thread(target=_cleanup_worker, daemon=True, name="file-cleanup")
    t.start()
    app.logger.info(
        f"文件清理线程已启动（保留期 {_FILE_MAX_AGE_SECONDS // 3600} 小时，"
        f"扫描间隔 {_CLEANUP_INTERVAL_SECONDS // 3600} 小时）。"
    )


# --- Main ---
if __name__ == "__main__":
    test_neo4j_connection()
    _start_cleanup_thread()
    app.run(debug=True, host="0.0.0.0", port=5001, threaded=True, use_reloader=False)