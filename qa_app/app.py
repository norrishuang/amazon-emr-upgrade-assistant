from flask import Flask, render_template, request, jsonify, send_from_directory
from opensearchpy import OpenSearch, RequestsHttpConnection
import os
from dotenv import load_dotenv
import json

load_dotenv()

app = Flask(__name__)

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

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/search', methods=['POST'])
def search():
    query = request.json.get('query', '')
    
    # 构建 OpenSearch 查询
    search_query = {
        "query": {
            "neural": {
                "embedding": {
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
                "timeout": 15
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
        
        # 分割思考过程和最终答案
        thinking = ''
        answer = raw_answer
        
        if '</think>' in raw_answer:
            parts = raw_answer.split('</think>')
            thinking = parts[0].strip()
            answer = parts[1].replace('\n\n', '\n').strip() if len(parts) > 1 else ''
        else:
            answer = answer.replace('\n\n', '\n').strip()
            
        return jsonify({
            'success': True,
            'results': results,
            'thinking': thinking,
            'answer': answer
        })
        
    except Exception as e:
        return jsonify({
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

if __name__ == '__main__':
    app.run(debug=True)
