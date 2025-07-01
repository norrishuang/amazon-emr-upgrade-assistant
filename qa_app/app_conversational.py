from flask import Flask, render_template, request, jsonify, send_from_directory, session, redirect, url_for
from opensearchpy import OpenSearch, RequestsHttpConnection
import os
from dotenv import load_dotenv
import json
from datetime import datetime, timedelta
import json as json_module
import secrets
import boto3
from botocore.exceptions import ClientError
import logging
from logging.handlers import RotatingFileHandler
import sys

load_dotenv()

# 应用版本
APP_VERSION = "v0.1"

# 创建日志目录
log_dir = 'logs'
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

# 配置日志记录器
def setup_logger():
    logger = logging.getLogger('emr_assistant')
    logger.setLevel(logging.INFO)
    
    # 创建格式化器
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # 创建控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # 创建文件处理器（带滚动）
    file_handler = RotatingFileHandler(
        filename=os.path.join(log_dir, 'emr_assistant.log'),
        maxBytes=100*1024*1024,  # 100MB
        backupCount=30,
        encoding='utf-8'
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    return logger

# 初始化日志记录器
logger = setup_logger()

# 自定义JSON编码函数，确保中文字符不被转义
def custom_jsonify(data):
    return app.response_class(
        json_module.dumps(data, ensure_ascii=False),
        mimetype='application/json; charset=utf-8'
    )

def get_secret(secret_name, region_name='us-east-1'):
    """
    从 AWS Secrets Manager 获取密钥
    """
    session = boto3.session.Session()
    client = session.client(
        service_name='secretsmanager',
        region_name=region_name
    )
    logger.info(f"正在获取密钥: {secret_name}")
    try:
        get_secret_value_response = client.get_secret_value(
            SecretId=secret_name
        )
    except ClientError as e:
        logger.error(f"获取密钥失败: {str(e)}")
        raise e
    else:
        if 'SecretString' in get_secret_value_response:
            return json.loads(get_secret_value_response['SecretString'])
        else:
            logger.error("密钥值不是字符串类型")
            raise ValueError("Secret value is not a string")

# 应用配置
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'opensearch-rag-demo-secret-key')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=24)  # 设置session过期时间

# 从 Secrets Manager 获取 OpenSearch 认证信息
try:
    secret_name = os.getenv('OPENSEARCH_SECRET_NAME', 'opensearch_credentials')
    region_name = os.getenv('AWS_REGION', 'us-east-1')
    opensearch_credentials = get_secret(secret_name, region_name)
    
    # OpenSearch 客户端配置
    client = OpenSearch(
        hosts=[{'host': os.getenv('OPENSEARCH_HOST', 'localhost'), 'port': int(os.getenv('OPENSEARCH_PORT', 9200))}],
        http_auth=(opensearch_credentials['username'], opensearch_credentials['password']),
        use_ssl=True,
        verify_certs=False,
        ssl_show_warn=False,
        connection_class=RequestsHttpConnection,
        timeout=120
    )
    logger.info("OpenSearch 客户端初始化成功")
except Exception as e:
    logger.error(f"OpenSearch 客户端初始化失败: {str(e)}")
    raise

# 存储邀请码的字典，格式为 {invite_code: expiry_time}
invite_codes = {}

# 生成邀请码的函数
def generate_invite_code(expiry_hours=24):
    code = secrets.token_urlsafe(16)
    expiry_time = datetime.now() + timedelta(hours=expiry_hours)
    invite_codes[code] = expiry_time
    logger.info(f"生成新邀请码: {code}, 过期时间: {expiry_time}")
    return code

# 验证邀请码的函数
def verify_invite_code(code):
    if code not in invite_codes:
        logger.warning(f"无效的邀请码尝试: {code}")
        return False
    if datetime.now() > invite_codes[code]:
        logger.info(f"邀请码已过期: {code}")
        del invite_codes[code]
        return False
    logger.info(f"邀请码验证成功: {code}")
    return True

# 清理过期邀请码的函数
def cleanup_expired_codes():
    current_time = datetime.now()
    expired_codes = [code for code, expiry in invite_codes.items() if current_time > expiry]
    for code in expired_codes:
        del invite_codes[code]
    if expired_codes:
        logger.info(f"清理过期邀请码: {len(expired_codes)} 个")

@app.route('/login', methods=['GET', 'POST'])
def login():
    # 如果已经登录，重定向到主页
    if session.get('authenticated'):
        logger.info("用户已登录，重定向到主页")
        return redirect(url_for('index'))
        
    if request.method == 'GET':
        logger.info("访问登录页面")
        return render_template('login.html')
    
    data = request.get_json()
    invite_code = data.get('inviteCode')
    
    if not invite_code:
        logger.warning("登录尝试：未提供邀请码")
        return custom_jsonify({
            'success': False,
            'error': '请输入邀请码'
        })
    
    if verify_invite_code(invite_code):
        session.permanent = True  # 设置session为永久性
        session['authenticated'] = True
        logger.info(f"用户登录成功，邀请码: {invite_code}")
        return custom_jsonify({
            'success': True
        })
    else:
        logger.warning(f"登录失败：无效的邀请码: {invite_code}")
        return custom_jsonify({
            'success': False,
            'error': '邀请码无效或已过期'
        })

@app.route('/')
def index():
    if not session.get('authenticated'):
        logger.info("未登录用户尝试访问主页，重定向到登录页")
        return redirect(url_for('login'))
    logger.info("用户访问主页")
    return render_template('index_conversational.html', app_version=APP_VERSION)

@app.route('/logout')
def logout():
    logger.info("用户登出")
    session.clear()
    return redirect(url_for('login'))

@app.route('/create_session', methods=['POST'])
def create_session():
    try:
        logger.info("创建新会话")
        # 调用 OpenSearch 创建新的 memory
        response = client.transport.perform_request(
            method='POST',
            url='/_plugins/_ml/memory',
            body={}
        )
        
        memory_id = response.get('memory_id')
        if not memory_id:
            logger.error("创建会话失败：未获取到 memory_id")
            raise ValueError("创建会话失败：未获取到 memory_id")
            
        logger.info(f"会话创建成功: {memory_id}")
        return custom_jsonify({
            'success': True,
            'memory_id': memory_id
        })
    except Exception as e:
        logger.error(f"创建会话失败: {str(e)}")
        return custom_jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/search', methods=['POST'])
def search():
    query = request.json.get('query', '')
    memory_id = request.json.get('memory_id', '')
    pipeline = request.json.get('pipeline', 'my-conversation-search-pipeline-deepseek-zh')
    
    logger.info(f"收到搜索请求 - 查询: {query}, 会话ID: {memory_id}, 管道: {pipeline}")
    
    if not memory_id:
        logger.warning("搜索请求：未提供会话ID")
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
                                "k": 10
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
        },
        "highlight": {
            "pre_tags": ["<strong>"],
            "post_tags": ["</strong>"],
            "fields": {"text": {}}
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
        logger.info(f"执行搜索 - 管道: {pipeline}")
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
            
        logger.info(f"搜索成功 - 找到 {len(results)} 个结果")
        return custom_jsonify({
            'success': True,
            'results': results,
            'thinking': thinking,
            'answer': answer
        })
        
    except Exception as e:
        logger.error(f"搜索失败: {str(e)}")
        return custom_jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/delete_session', methods=['POST'])
def delete_session():
    memory_id = request.json.get('memory_id', '')
    
    if not memory_id:
        logger.warning("删除会话请求：未提供会话ID")
        return custom_jsonify({
            'success': False,
            'error': '未提供会话ID'
        }), 400
    
    try:
        logger.info(f"删除会话: {memory_id}")
        # 调用 OpenSearch 删除 memory
        response = client.transport.perform_request(
            method='DELETE',
            url=f'/_plugins/_ml/memory/{memory_id}'
        )
        
        logger.info(f"会话删除成功: {memory_id}")
        return custom_jsonify({
            'success': True,
            'message': '会话已删除'
        })
    except Exception as e:
        logger.error(f"删除会话失败: {str(e)}")
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
    logger.info(f"生成新邀请码: {code}")
    return custom_jsonify({
        'success': True,
        'code': code,
        'expires': invite_codes[code].isoformat()
    })

if __name__ == '__main__':
    # 生成一个测试用的邀请码
    test_code = generate_invite_code()
    logger.info(f"应用启动 - 测试邀请码: {test_code}")
    logger.info(f"应用启动 - 过期时间: {invite_codes[test_code]}")
    
    app.run(host='0.0.0.0', port=5001, debug=False)
