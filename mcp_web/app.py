import os
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import requests
from datetime import timedelta
import secrets
import boto3
import json

# 配置
MCP_SERVER_URL = os.getenv('MCP_SERVER_URL', 'http://localhost:5100')
MCP_API_KEY = os.getenv('MCP_API_KEY', 'your-mcp-api-key')

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('WEB_SECRET_KEY', 'mcp-web-secret-key')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=24)

# 简单的邀请码机制
invite_codes = {}
def generate_invite_code(expiry_hours=24):
    code = secrets.token_urlsafe(16)
    invite_codes[code] = True
    return code

def verify_invite_code(code):
    return invite_codes.get(code, False)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('authenticated'):
        return redirect(url_for('index'))
    if request.method == 'GET':
        return render_template('login.html')
    data = request.form
    invite_code = data.get('inviteCode')
    if not invite_code:
        return render_template('login.html', error='请输入邀请码')
    if verify_invite_code(invite_code):
        session['authenticated'] = True
        return redirect(url_for('index'))
    else:
        return render_template('login.html', error='邀请码无效或已过期')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/')
def index():
    if not session.get('authenticated'):
        return redirect(url_for('login'))
    return render_template('index.html')

@app.route('/search', methods=['POST'])
def search():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': '未登录'}), 401
    query = request.json.get('query', '')
    pipeline = request.json.get('pipeline', 'my-conversation-search-pipeline-deepseek-zh')
    try:
        resp = requests.post(
            f"{MCP_SERVER_URL}/search",
            headers={
                'x-api-key': MCP_API_KEY,
                'Content-Type': 'application/json'
            },
            json={
                'query': query,
                'pipeline': pipeline
            },
            timeout=30
        )
        return jsonify(resp.json())
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/generate_invite_code', methods=['POST'])
def generate_code():
    code = generate_invite_code()
    return jsonify({'success': True, 'code': code})

@app.route('/answer', methods=['POST'])
def answer():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': '未登录'}), 401
    data = request.get_json()
    query = data.get('query', '')
    model = data.get('model', 'anthropic.claude-v2')
    ak = data.get('ak', '')
    sk = data.get('sk', '')
    mcp_url = data.get('mcp_url', '')
    mcp_key = data.get('mcp_key', '')
    # 1. 先请求 MCP Server
    try:
        mcp_resp = requests.post(
            mcp_url,
            headers={
                'x-api-key': mcp_key,
                'Content-Type': 'application/json'
            },
            json={
                'query': query,
                'messages': [{'role': 'user', 'content': query}],
                'user_id': session.get('user_id', 'web-user'),
                'context': {}
            },
            timeout=30
        )
        mcp_data = mcp_resp.json()
        recall = '\n'.join([r['text'] for r in mcp_data.get('results', [])])
    except Exception as e:
        return jsonify({'success': False, 'error': f'MCP Server 调用失败: {str(e)}'}), 500
    # 2. 用 Bedrock 生成答案
    try:
        session_bedrock = boto3.Session(
            aws_access_key_id=ak,
            aws_secret_access_key=sk,
            region_name='us-east-1'
        )
        bedrock = session_bedrock.client('bedrock-runtime')
        # 构造 prompt
        prompt = f"你是 Amazon EMR 升级助手，请结合以下知识库内容回答用户问题。\n知识库内容：{recall}\n用户问题：{query}"
        if model.startswith('anthropic.'):
            body = {
                "prompt": prompt,
                "max_tokens_to_sample": 512,
                "temperature": 0.2
            }
            response = bedrock.invoke_model(
                modelId=model,
                body=json.dumps(body)
            )
            answer = response['body'].read().decode('utf-8')
        elif model.startswith('amazon.') or model.startswith('meta.'):
            body = {
                "inputText": prompt,
                "textGenerationConfig": {
                    "maxTokenCount": 512,
                    "temperature": 0.2
                }
            }
            response = bedrock.invoke_model(
                modelId=model,
                body=json.dumps(body)
            )
            answer = response['body'].read().decode('utf-8')
        else:
            answer = '暂不支持该模型调用。'
        return jsonify({'success': True, 'answer': answer, 'recall': recall})
    except Exception as e:
        return jsonify({'success': False, 'error': f'Bedrock 调用失败: {str(e)}', 'recall': recall})

if __name__ == '__main__':
    # 启动时生成一个测试邀请码
    test_code = generate_invite_code()
    print(f"测试邀请码: {test_code}")
    app.run(host='0.0.0.0', port=5200, debug=True) 