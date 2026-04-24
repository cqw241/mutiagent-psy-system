import assert from 'node:assert/strict'
import test from 'node:test'

import { buildRagRetrievalRows } from './TracePanel.helpers.js'

test('buildRagRetrievalRows maps RAG judgments to display rows', () => {
  const rows = buildRagRetrievalRows({
    agent_judgments: {
      rag_retriever: {
        enabled: true,
        reference_found: true,
      },
      peer_support_retriever: {
        enabled: true,
        reference_found: false,
      },
    },
  })

  assert.deepEqual(rows, [
    {
      key: 'rag_retriever',
      label: '专业案例库',
      status: '已命中',
      tone: 'hit',
    },
    {
      key: 'peer_support_retriever',
      label: '同辈支持库',
      status: '未命中',
      tone: 'miss',
    },
  ])
})
