Use the Open WebUI MCP tools to answer a RAG-backed question.

$ARGUMENTS

Steps:
1. If no collection name is apparent from the arguments, call `list_collections` first and present the options.
2. Call `rag_query` with the question and the resolved collection name.
3. Present the answer clearly. Note which collection and model was used.
