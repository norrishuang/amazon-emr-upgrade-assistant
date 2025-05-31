from flask import Flask, render_template, request, jsonify, send_from_directory
from opensearchpy import OpenSearch, RequestsHttpConnection
import os
from dotenv import load_dotenv
from werkzeug.utils import secure_filename
import PyPDF2
import docx
import json
from datetime import datetime
import json as json_module

load_dotenv()

# 自定义JSON编码函数，确保中文字符不被转义
def custom_jsonify(data):
    return app.response_class(
        json_module.dumps(data, ensure_ascii=False),
        mimetype='application/json; charset=utf-8'
    )

# 应用配置
app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 64 * 1024 * 1024  # 限制上传文件大小为64MB
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'opensearch-rag-demo-secret-key')

# 确保上传目录存在
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

ALLOWED_EXTENSIONS = {'txt', 'pdf', 'doc', 'docx'}

# OpenSearch 会话记忆 ID
MEMORY_ID = os.getenv('OPENSEARCH_MEMORY_ID', '')

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def split_text(text, max_length=500):
    """将文本分割成较小的块"""
    sentences = text.split('。')
    chunks = []
    current_chunk = ""
    
    for sentence in sentences:
        if len(current_chunk) + len(sentence) < max_length:
            current_chunk += sentence + "。"
        else:
            if current_chunk:
                chunks.append(current_chunk)
            current_chunk = sentence + "。"
    
    if current_chunk:
        chunks.append(current_chunk)
    
    return chunks

def extract_text_from_pdf(file_path):
    """从PDF文件中提取文本"""
    try:
        text = ""
        with open(file_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            for page in pdf_reader.pages:
                try:
                    # 提取文本并处理编码
                    page_text = page.extract_text()
                    if page_text:
                        # 移除特殊字符和无效的 XML 字符
                        page_text = ''.join(char for char in page_text if ord(char) >= 32)
                        text += page_text + "\n"
                except Exception as page_error:
                    print(f"处理 PDF 页面时出错: {str(page_error)}")
                    continue
        
        # 如果没有提取到任何文本，抛出异常
        if not text.strip():
            raise ValueError("无法从 PDF 文件中提取文本内容")
            
        return text.strip()
    except Exception as e:
        raise ValueError(f"PDF 文件处理失败: {str(e)}")

def extract_text_from_docx(file_path):
    """从DOCX文件中提取文本"""
    doc = docx.Document(file_path)
    text = ""
    for para in doc.paragraphs:
        text += para.text + "\n"
    return text

# OpenSearch 客户端配置
client = OpenSearch(
    hosts=[{'host': os.getenv('OPENSEARCH_HOST', 'localhost'), 'port': int(os.getenv('OPENSEARCH_PORT', 9200))}],
    http_auth=(os.getenv('OPENSEARCH_USER', 'admin'), os.getenv('OPENSEARCH_PASSWORD', 'admin')),
    use_ssl=True,
    verify_certs=False,
    ssl_show_warn=False,
    connection_class=RequestsHttpConnection,
    timeout=120
)

# 定义 ingestion pipeline
ingest_pipeline_name = 'text-embedding-pipeline'
ingest_pipeline_definition = {
    "processors": [
        {
            "text_embedding": {
                "model_id": os.getenv('OPENSEARCH_EMBEDDING_MODEL_ID', '-kB2sZUB0LCOh9zdNaiU'),
                "field_map": {
                    "text": "text_embedding"
                }
            }
        }
    ]
}

# 创建或更新 ingestion pipeline
try:
    client.ingest.put_pipeline(
        id=ingest_pipeline_name,
        body=ingest_pipeline_definition
    )
except Exception as e:
    print(f"创建 ingestion pipeline 失败: {str(e)}")

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': '没有文件被上传'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'error': '没有选择文件'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'success': False, 'error': '不支持的文件类型'}), 400
    
    file_path = None
    try:
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)
        
        # 根据文件类型提取文本
        text = ""
        if filename.lower().endswith('.pdf'):
            text = extract_text_from_pdf(file_path)
        elif filename.lower().endswith('.docx'):
            text = extract_text_from_docx(file_path)
        elif filename.lower().endswith('.txt'):
            with open(file_path, 'r', encoding='utf-8') as f:
                text = f.read()
        
        # 验证提取的文本
        if not text or not text.strip():
            raise ValueError("无法从文件中提取有效文本内容")
        
        # 分割文本
        chunks = split_text(text)
        if not chunks:
            raise ValueError("文本分割后没有有效内容")
        
        # 将分割后的文本块写入 OpenSearch
        success_count = 0
        for i, chunk in enumerate(chunks):
            try:
                if not chunk.strip():
                    continue
                    
                document = {
                    'text': chunk.strip(),
                    'source': filename,
                    'chunk_id': i
                }
                
                # 使用配置的 ingestion pipeline 写入 OpenSearch
                client.index(
                    index=os.getenv('OPENSEARCH_INDEX', 'opensearch_kl_index'),
                    body=document,
                    pipeline=ingest_pipeline_name
                )
                success_count += 1
            except Exception as chunk_error:
                print(f"处理第 {i} 个文本块时出错: {str(chunk_error)}")
                continue
        
        if success_count == 0:
            raise ValueError("没有成功处理任何文本块")
        
        return jsonify({
            'success': True,
            'message': f'文件处理完成，成功处理 {success_count} 个文本块，共 {len(chunks)} 个文本块'
        })
        
    except Exception as e:
        error_message = str(e)
        print(f"文件处理错误: {error_message}")
        return jsonify({
            'success': False,
            'error': f"文件处理失败: {error_message}"
        }), 500
    finally:
        # 确保清理临时文件
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception as cleanup_error:
                print(f"清理临时文件失败: {str(cleanup_error)}")

@app.route('/')
def index():
    return render_template('index_conversational.html')



@app.route('/search', methods=['POST'])
def search():
    query = request.json.get('query', '')
    
    # 构建 OpenSearch 查询，使用 memory_id 实现会话记忆
    search_query = {
        "query": {
            "neural": {
                "text_embedding": {
                    "query_text": query,
                    "model_id": os.getenv('OPENSEARCH_EMBEDDING_MODEL_ID', '-kB2sZUB0LCOh9zdNaiU'),
                    "k": 5
                }
            }
        },
        "size": 3,
        "_source": [
            "text"
        ],
        "ext": {
            "generative_qa_parameters": {
                "llm_model": "bedrock/claude",
                "llm_question": query,
                "context_size": 5,
                "timeout": 100,
                "memory_id": MEMORY_ID,
                "message_size": 2  # 保留最近10条消息的上下文
            }
        }
    }
    
    try:
        # 执行搜索
        response = client.search(
            body=search_query,
            index=os.getenv('OPENSEARCH_INDEX', 'opensearch_kl_index'),
            params={'search_pipeline': 'my-conversation-search-pipeline-deepseek-zh'}
        )
        
        # 打印完整的 OpenSearch 响应到控制台
        print("\n=== OpenSearch 完整响应 ===")
        print(json.dumps(response, ensure_ascii=False, indent=2))
        print("=== OpenSearch 响应结束 ===\n")
        
        # 处理搜索结果
        hits = response['hits']['hits']
        results = []
        
        for hit in hits:
            result = {
                'text': hit['_source'].get('text', ''),
                'score': hit['_score']
            }
            results.append(result)
            
        # 获取生成式问答结果和思考过程
        raw_answer = response.get('ext', {}).get('retrieval_augmented_generation', {}).get('answer', '')
        
        # 确保raw_answer是字符串类型
        if isinstance(raw_answer, bytes):
            raw_answer = raw_answer.decode('utf-8')
        
        # 打印生成式问答原始回答
        print("\n=== 生成式问答原始回答 ===")
        print(f"raw_answer: {raw_answer}")
        print("=== 原始回答结束 ===\n")
        
        # 分割思考过程和最终答案
        thinking = ''
        answer = raw_answer
        
        if '</think>' in raw_answer:
            parts = raw_answer.split('</think>')
            thinking = parts[0].strip()
            # 处理可能存在的多余换行符
            answer = parts[1].replace('\n\n', '\n').strip() if len(parts) > 1 else ''
            
            # 打印分割后的思考过程和答案
            print("\n=== 分割后的内容 ===")
            print(f"思考过程: {thinking}")
            print(f"最终答案: {answer}")
            print("=== 分割结束 ===\n")
        else:
            # 如果没有思考过程标记，确保答案也进行清理
            answer = answer.replace('\n\n', '\n').strip()
            
        # 使用自定义的JSON编码函数确保中文字符不被转义
        return custom_jsonify({
            'success': True,
            'results': results,
            'thinking': thinking,
            'answer': answer
        })
        
    except Exception as e:
        return custom_jsonify({
            'success': False,
            'error': str(e)
        }), 500

# 注意：使用 OpenSearch 的 memory_id 功能，不再需要在应用中管理会话历史

# 添加缓存控制
@app.after_request
def add_header(response):
    if 'Cache-Control' not in response.headers:
        response.headers['Cache-Control'] = 'public, max-age=300'
    return response

# 静态文件路由
@app.route('/static/<path:filename>')
def serve_static(filename):
    response = send_from_directory('static', filename)
    response.headers['Cache-Control'] = 'public, max-age=3600'
    return response

if __name__ == '__main__':
    app.run(debug=True, port=5001)  # 使用不同的端口，避免与原应用冲突
