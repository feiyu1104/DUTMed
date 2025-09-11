import os
import json
import io
import threading
import queue  # For thread-safe communication
from flask import Flask, render_template, request, Response, stream_with_context, jsonify, send_from_directory
import q_a  # Assuming q_a.py is in the same directory or accessible via PYTHONPATH
from rich.console import Console
from ansi2html import Ansi2HTMLConverter  # For converting rich's ANSI output to HTML
from py2neo import Graph as Py2neoGraph  # Explicit import for clarity
from image_segmentation import image_segmentation_service  # Import image segmentation service
from image_description import image_description_service  # Import image description service
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# --- Flask App Setup ---
app = Flask(__name__)
app.secret_key = os.urandom(24)  # Still needed for flashing messages, etc.

# Store the original print and console from q_a module to restore later
original_q_a_console_print = None
original_q_a_console_file = None
current_sse_yield_callback = None

# --- Helper for Log Streaming ---
def sse_log_print(*args, **kwargs):
    """
    Monkey-patched print function for q_a.console.
    Captures rich output and yields it for SSE.
    """
    global current_sse_yield_callback
    if not current_sse_yield_callback:
        if original_q_a_console_print:
            original_q_a_console_print(*args, **kwargs)
        return

    s_io = io.StringIO()
    if args and hasattr(args[0], '__rich_console__'):
        temp_console_for_export = Console(file=s_io, record=True, width=100, force_terminal=False, color_system=None)
        temp_console_for_export.print(*args, **kwargs)
        s_io.seek(0)
        s_io.truncate(0)
        recorded_console = Console(file=s_io, record=True, width=100)
        recorded_console.print(*args, **kwargs)
        html_content = recorded_console.export_html(inline_styles=True, code_format="<pre class=\"code\">{code}</pre>")

        if "<!DOCTYPE html>" in html_content:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html_content, 'html.parser')
            body_content = soup.body.decode_contents() if soup.body else html_content
            body_content = body_content.replace("background-color:#ffffff;", "", 1).replace("color:#000000;", "", 1)
            current_sse_yield_callback(f"data: {json.dumps({'type': 'log_html', 'content': body_content})}\n\n")
    else:
        temp_console_for_ansi = Console(file=s_io, force_terminal=True, color_system="truecolor", width=100)
        temp_console_for_ansi.print(*args, **kwargs)
        ansi_output = s_io.getvalue()
        conv = Ansi2HTMLConverter(inline=True, scheme="solarized", linkify=False, dark_bg=True)
        html_output = conv.convert(ansi_output, full=False)
        log_content = f'<div class="log-entry-raw">{html_output}</div>'
        current_sse_yield_callback(f"data: {json.dumps({'type': 'log_html', 'content': log_content})}\n\n")

    if original_q_a_console_print:
        original_q_a_console_print(*args, **kwargs)


# --- Routes ---
@app.route("/", methods=["GET"])
def index():
    # ✅ 从环境变量获取 Neo4j 配置，传给前端显示
    neo4j_config = {
        "uri": os.getenv("NEO4J_URI"),
        "user": os.getenv("NEO4J_USER"),
    }
    return render_template("index.html", neo4j_config=neo4j_config)


@app.route("/ask", methods=["POST"])
def ask_question():
    data = request.json
    question_text = data.get("question")
    enable_multi_hop = data.get("enable_multi_hop", True)
    search_budget = data.get("search_budget", "Deeper")

    if not question_text:
        return Response(json.dumps({"error": "No question provided."}), status=400, mimetype='application/json')

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

        def rag_worker(q, question, multi_hop, budget, finish_event):
            original_q_a_console_file = None
            worker_sse_wrapper = SseLogStreamWrapper(q)

            try:
                if hasattr(q_a, 'console') and hasattr(q_a.console, 'file'):
                    original_q_a_console_file = q_a.console.file

                if hasattr(q_a, 'console'):
                    q_a.console.file = worker_sse_wrapper
                else:
                    q.put({'type': 'error', 'content': 'Internal error: q_a.console not found.'})
                    finish_event.set()
                    return

                # ✅ Use environment variables for Neo4j config
                rag_system = q_a.Neo4jRAGSystem(
                    neo4j_uri=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
                    neo4j_user=os.getenv("NEO4J_USER", "neo4j"),
                    neo4j_password=os.getenv("NEO4J_PASSWORD", "123456789"),
                    enable_multi_hop=multi_hop,
                    search_budget_mode=budget
                )

                final_answer = rag_system.answer_question(question)
                worker_sse_wrapper.flush()
                q.put({'type': 'answer', 'content': final_answer})

            except Exception as e:
                app.logger.error(f"Error in RAG worker thread: {e}", exc_info=True)
                try:
                    worker_sse_wrapper.flush()
                except:
                    pass
                q.put({'type': 'error', 'content': f"An error occurred: {str(e)}"})
            finally:
                if original_q_a_console_file is not None and hasattr(q_a, 'console'):
                    q_a.console.file = original_q_a_console_file
                finish_event.set()
                q.put({'type': 'finished'})

        worker_thread = threading.Thread(target=rag_worker, args=(
            message_queue, question_text, enable_multi_hop, search_budget, finished_signal))
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

        app.logger.info(f"图像分割和描述完成: {segmented_path}")
        return jsonify({
            "success": True,
            "original_image": f"/uploads/{os.path.basename(original_path)}",
            "segmented_image": f"/segmented/{os.path.basename(segmented_path)}",
            "segmentation_info": seg_info,
            "description": description
        })

    except Exception as e:
        app.logger.error(f"图像分割过程中出错: {e}", exc_info=True)
        return jsonify({"error": f"Image segmentation error: {str(e)}"}), 500


@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory('static/uploads', filename)


@app.route('/segmented/<filename>')
def segmented_file(filename):
    return send_from_directory('static/segmented', filename)


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
        # Optional: sys.exit(1) if you want to crash on failure


# --- Main ---
if __name__ == "__main__":
    test_neo4j_connection()  # Test connection before starting server
    app.run(debug=True, host="0.0.0.0", port=5001, threaded=True, use_reloader=False)