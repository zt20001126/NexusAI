import assert from 'node:assert/strict'
import { fileURLToPath } from 'node:url'
import test from 'node:test'
import { createServer } from 'vite'

test('resume profile summary uses manual values and the first filled degree', async (context) => {
  const server = await createServer({
    configFile: fileURLToPath(new URL('../vite.config.ts', import.meta.url)),
    server: { middlewareMode: true },
    appType: 'custom',
    logLevel: 'silent',
  })
  context.after(() => server.close())

  const { createResumeProfileSummary } = await server.ssrLoadModule(
    '/src/features/resume/model/profileSummary.ts',
  )
  const summary = createResumeProfileSummary(
    {
      name: '林知远',
      phone: ' 13800138000 ',
      email: 'lin@example.com',
      intended_position: '高级全栈工程师',
      age: 29,
      work_experience_years: 5,
      photo_id: null,
    },
    [{ degree: '   ' }, { degree: '硕士' }, { degree: '本科' }],
  )

  assert.deepEqual(summary, {
    positionItems: ['高级全栈工程师', '5年工作经验'],
    contactItems: ['13800138000', 'lin@example.com', '29岁', '硕士'],
  })
})

test('resume profile summary omits blank values and empty rows', async (context) => {
  const server = await createServer({
    configFile: fileURLToPath(new URL('../vite.config.ts', import.meta.url)),
    server: { middlewareMode: true },
    appType: 'custom',
    logLevel: 'silent',
  })
  context.after(() => server.close())

  const { createResumeProfileSummary } = await server.ssrLoadModule(
    '/src/features/resume/model/profileSummary.ts',
  )
  const summary = createResumeProfileSummary(
    {
      name: '',
      phone: '  ',
      email: '',
      intended_position: ' ',
      age: null,
      work_experience_years: null,
      photo_id: null,
    },
    [{ degree: '' }, { degree: '  ' }],
  )

  assert.deepEqual(summary, { positionItems: [], contactItems: [] })
})
