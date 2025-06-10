from flask import Flask, render_template, request, jsonify, send_from_directory, session, redirect, url_for
from opensearchpy import OpenSearch, RequestsHttpConnection
import os
from dotenv import load_dotenv
import json
from datetime import datetime, timedelta
import json as json_module
import secrets

load_dotenv()

# 自定义JSON编码函数，确保中文字符不被转义
def custom_jsonify(data):
    return app.response_class(
        json_module.dumps(data, ensure_ascii=False),
        mimetype='application/json; charset=utf-8'
    )

# 应用配置
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'opensearch-rag-demo-secret-key')

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

# 存储邀请码的字典，格式为 {invite_code: expiry_time}
invite_codes = {}

# 生成邀请码的函数
def generate_invite_code(expiry_hours=24):
    code = secrets.token_urlsafe(16)
    expiry_time = datetime.now() + timedelta(hours=expiry_hours)
    invite_codes[code] = expiry_time
    return code

# 验证邀请码的函数
def verify_invite_code(code):
    if code not in invite_codes:
        return False
    if datetime.now() > invite_codes[code]:
        del invite_codes[code]
        return False
    return True

# 清理过期邀请码的函数
def cleanup_expired_codes():
    current_time = datetime.now()
    expired_codes = [code for code, expiry in invite_codes.items() if current_time > expiry]
    for code in expired_codes:
        del invite_codes[code]

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return render_template('login.html')
    
    data = request.get_json()
    invite_code = data.get('inviteCode')
    
    if not invite_code:
        return custom_jsonify({
            'success': False,
            'error': '请输入邀请码'
        })
    
    if verify_invite_code(invite_code):
        session['authenticated'] = True
        return custom_jsonify({
            'success': True
        })
    else:
        return custom_jsonify({
            'success': False,
            'error': '邀请码无效或已过期'
        })

@app.route('/')
def index():
    if not session.get('authenticated'):
        return redirect(url_for('login'))
    return render_template('index_conversational.html')

@app.route('/create_session', methods=['POST'])
def create_session():
    try:
        # 调用 OpenSearch 创建新的 memory
        response = client.transport.perform_request(
            method='POST',
            url='/_plugins/_ml/memory',
            body={}
        )
        
        memory_id = response.get('memory_id')
        if not memory_id:
            raise ValueError("创建会话失败：未获取到 memory_id")
            
        return custom_jsonify({
            'success': True,
            'memory_id': memory_id
        })
    except Exception as e:
        return custom_jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/search', methods=['POST'])
def search():
    query = request.json.get('query', '')
    memory_id = request.json.get('memory_id', '')
    pipeline = request.json.get('pipeline', 'my-conversation-search-pipeline-deepseek-zh')
    
    if not memory_id:
        return custom_jsonify({
            'success': False,
            'error': '未提供会话ID'
        }), 400
    
    # 构建基础查询
    search_query = {
        "query": {
            "hybrid": {
                "queries": [
                    {
                        "neural": {
                            "embedding": {
                                "query_text": query,
                                "model_id": os.getenv('OPENSEARCH_EMBEDDING_MODEL_ID', '-kB2sZUB0LCOh9zdNaiU'),
                                "k": 5
                            }
                        }
                    },
                    {
                        "match": {
                            "text": {
                                "query": query
                            }
                        }
                    }
                ]
            }
        },
        "size": 5,
        "_source": [
            "text"
        ],
        "ext": {
            "generative_qa_parameters": {
                "llm_model": "bedrock/claude",
                "llm_question": query,
                "context_size": 5,
                "timeout": 100,
                "memory_id": memory_id,
                "message_size": 3
            }
        }
    }
    
    # 如果是重排序管道，添加重排序参数
    if pipeline == 'conversation_and_rerank_pipeline_bedrock':
        search_query["ext"]["rerank"] = {
            "query_context": {
                "query_text": query
            }
        }
    
    try:
        # 执行搜索
        response = client.search(
            body=search_query,
            index=os.getenv('OPENSEARCH_INDEX', 'opensearch_kl_index'),
            params={'search_pipeline': pipeline}
        )
        
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
        
        # 分割思考过程和最终答案
        thinking = ''
        answer = raw_answer
        
        if '</think>' in raw_answer:
            parts = raw_answer.split('</think>')
            thinking = parts[0].strip()
            answer = parts[1].replace('\n\n', '\n').strip() if len(parts) > 1 else ''
        else:
            answer = answer.replace('\n\n', '\n').strip()
            
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

@app.route('/delete_session', methods=['POST'])
def delete_session():
    memory_id = request.json.get('memory_id', '')
    
    if not memory_id:
        return custom_jsonify({
            'success': False,
            'error': '未提供会话ID'
        }), 400
    
    try:
        # 调用 OpenSearch 删除 memory
        response = client.transport.perform_request(
            method='DELETE',
            url=f'/_plugins/_ml/memory/{memory_id}'
        )
        
        return custom_jsonify({
            'success': True,
            'message': '会话已删除'
        })
    except Exception as e:
        return custom_jsonify({
            'success': False,
            'error': str(e)
        }), 500

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

# 添加生成邀请码的路由（仅用于测试）
@app.route('/generate_invite_code', methods=['POST'])
def generate_code():
    code = generate_invite_code()
    return custom_jsonify({
        'success': True,
        'code': code,
        'expires': invite_codes[code].isoformat()
    })

if __name__ == '__main__':
    # 生成一个测试用的邀请码
    test_code = generate_invite_code()
    print(f"测试邀请码: {test_code}")
    print(f"过期时间: {invite_codes[test_code]}")
    
    app.run(debug=True, port=5001)
