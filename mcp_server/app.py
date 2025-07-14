import os
import json
import boto3
from botocore.exceptions import ClientError
from typing import Any
from dotenv import load_dotenv
from opensearchpy import OpenSearch, RequestsHttpConnection
from mcp.server.fastmcp import FastMCP

load_dotenv()

def get_secret(secret_name, region_name='us-east-1'):
    """
    从 AWS Secrets Manager 获取密钥
    """
    session = boto3.session.Session()
    client = session.client(
        service_name='secretsmanager',
        region_name=region_name
    )
    try:
        get_secret_value_response = client.get_secret_value(
            SecretId=secret_name
        )
    except ClientError as e:
        print(f"获取密钥失败: {str(e)}")
        raise e
    else:
        if 'SecretString' in get_secret_value_response:
            return json.loads(get_secret_value_response['SecretString'])
        else:
            print("密钥值不是字符串类型")
            raise ValueError("Secret value is not a string")

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
    print("OpenSearch 客户端初始化成功")
except Exception as e:
    print(f"OpenSearch 客户端初始化失败: {str(e)}")
    raise

mcp = FastMCP("opensearch_mcp_server")

@mcp.tool()
async def search_context(
    query: str,
    user_id: str = "",
    pipeline: str = "my-conversation-search-pipeline-deepseek-zh"
) -> str:
    """
    用于检索 OpenSearch 上的内容并返回前3条结果拼接的答案。

    Args:
        query: 检索的查询内容
        user_id: 用户ID（可选）
        pipeline: OpenSearch 检索 pipeline 名称（可选）

    Returns:
        answer: 检索结果拼接的字符串
    """
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
        "size": 10,
        "_source": [
            "text"
        ],
        "ext": {
            "generative_qa_parameters": {
                "llm_model": "bedrock/claude",
                "llm_question": query,
                "context_size": 10,
                "timeout": 100
            }
        },
        "highlight": {
            "pre_tags": ["<strong>"],
            "post_tags": ["</strong>"],
            "fields": {"text": {}}
        }
    }
    try:
        response = client.search(
            body=search_query,
            index=os.getenv('OPENSEARCH_INDEX', 'opensearch_kl_index'),
            params={'search_pipeline': pipeline}
        )
        hits = response['hits']['hits']
        results = [{
            'text': hit['_source'].get('text', ''),
            'score': hit['_score']
        } for hit in hits]
        answer = '\n'.join([r['text'] for r in results[:3]])
        return answer
    except Exception as e:
        return f"检索失败: {str(e)}"

if __name__ == "__main__":
    mcp.run(transport='stdio')