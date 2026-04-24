const RAG_RETRIEVAL_SOURCES = [
  {
    key: 'rag_retriever',
    label: '专业案例库',
  },
  {
    key: 'peer_support_retriever',
    label: '同辈支持库',
  },
]

function formatRagRetrievalStatus(judgment) {
  if (!judgment) {
    return {
      status: '等待回合',
      tone: 'pending',
    }
  }

  if (!judgment.enabled) {
    return {
      status: '未启用',
      tone: 'disabled',
    }
  }

  if (judgment.reference_found) {
    return {
      status: '已命中',
      tone: 'hit',
    }
  }

  return {
    status: '未命中',
    tone: 'miss',
  }
}

export function buildRagRetrievalRows(trace) {
  const agentJudgments = trace?.agent_judgments ?? {}

  return RAG_RETRIEVAL_SOURCES.map((source) => {
    const status = formatRagRetrievalStatus(agentJudgments[source.key])

    return {
      key: source.key,
      label: source.label,
      ...status,
    }
  })
}
