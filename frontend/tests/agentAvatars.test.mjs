import assert from 'node:assert/strict'
import { fileURLToPath } from 'node:url'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import test from 'node:test'
import { createServer } from 'vite'

test('conversation welcome and sidebar use their current agent avatar', async (context) => {
  const server = await createServer({
    configFile: fileURLToPath(new URL('../vite.config.ts', import.meta.url)),
    server: { middlewareMode: true },
    appType: 'custom',
    logLevel: 'silent',
  })
  context.after(() => server.close())

  const [{ default: AgentAvatar }, { default: MessageList }, { default: ConversationSidebar }] = await Promise.all([
    server.ssrLoadModule('/src/features/chat/components/AgentAvatar.tsx'),
    server.ssrLoadModule('/src/features/chat/components/MessageList.tsx'),
    server.ssrLoadModule('/src/features/chat/components/ConversationSidebar.tsx'),
  ])
  const agent = 'image_agent'
  const expectedAvatar = renderToStaticMarkup(createElement(AgentAvatar, { agent }))
  const secondAgent = 'research_agent'
  const expectedSecondAvatar = renderToStaticMarkup(createElement(AgentAvatar, { agent: secondAgent }))
  const welcomeMarkup = renderToStaticMarkup(createElement(MessageList, {
    messages: [],
    loading: false,
    conversationId: null,
    agent,
  }))
  const sidebarMarkup = renderToStaticMarkup(createElement(ConversationSidebar, {
    conversations: [
      {
        conversation_id: 'conversation-1',
        title: '图片对话',
        created_at: '2026-10-16T00:00:00Z',
        updated_at: '2026-10-16T00:00:00Z',
        agent: agent,
      },
      {
        conversation_id: 'conversation-2',
        title: '文献检索',
        created_at: '2026-10-16T00:00:00Z',
        updated_at: '2026-10-16T00:00:00Z',
        agent: secondAgent,
      },
    ],
    activeConversationId: 'conversation-1',
    loading: false,
    hasMore: false,
    loadingMore: false,
    disabled: false,
    error: null,
    onCreate: () => {},
    onSelect: () => {},
    onLoadMore: () => {},
    onRetry: () => {},
  }))

  assert.match(expectedAvatar, /src="data:image\/svg\+xml/)
  await context.test('welcome panel shows the selected agent avatar', () => {
    assert.ok(welcomeMarkup.includes(expectedAvatar))
  })
  await context.test('conversation item shows its agent avatar', () => {
    assert.ok(sidebarMarkup.includes(expectedAvatar))
    assert.ok(sidebarMarkup.includes(expectedSecondAvatar))
  })
})
