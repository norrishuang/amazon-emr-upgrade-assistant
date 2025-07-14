import os
from typing import Any
from dotenv import load_dotenv
from opensearchpy import OpenSearch, RequestsHttpConnection
from mcp.server.fastmcp import FastMCP

load_dotenv()

# OpenSearch 客户端初始化
client = OpenSearch(
    hosts=[{'host': os.getenv('OPENSEARCH_HOST', 'localhost'), 'port': int(os.getenv('OPENSEARCH_PORT', 9200))}],
    http_auth=(os.getenv('OPENSEARCH_USER', 'admin'), os.getenv('OPENSEARCH_PASS', 'admin')),
    use_ssl=True,
    verify_certs=False,
    ssl_show_warn=False,
    connection_class=RequestsHttpConnection,
    timeout=120
)

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
        "_source": ["text"],
        "highlight": {
            "pre_tags": ["<strong>"],
            "post_tags": ["</strong>"],
            "fields": {"text": {}}
        }
    }
    try:
        print("OPENSEARCH_USER:", os.getenv('OPENSEARCH_USER'))
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