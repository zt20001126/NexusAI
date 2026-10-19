import assert from 'node:assert/strict'
import test from 'node:test'
import { toDisplayQuestionAnswers } from '../src/features/chat/model/questionAnswers.mjs'

test('uses question titles and displays multi-select values separately', () => {
  assert.deepEqual(
    toDisplayQuestionAnswers(
      { material: '不锈钢', use_cases: ['露营', '日常通勤'] },
      { material: '商品的主要材质是什么？', use_cases: '商品适用于哪些场景？' },
    ),
    [
      {
        questionId: 'material',
        title: '商品的主要材质是什么？',
        values: ['不锈钢'],
      },
      {
        questionId: 'use_cases',
        title: '商品适用于哪些场景？',
        values: ['露营', '日常通勤'],
      },
    ],
  )
})

test('uses readable legacy titles and humanizes unknown IDs', () => {
  assert.deepEqual(
    toDisplayQuestionAnswers({ frame_material: '碳纤维/碳素', custom_field: '答案', invalid: null }),
    [
      { questionId: 'frame_material', title: '拍框材质', values: ['碳纤维/碳素'] },
      { questionId: 'custom_field', title: 'Custom Field', values: ['答案'] },
    ],
  )
})
