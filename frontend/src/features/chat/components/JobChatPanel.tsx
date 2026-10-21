import { useEffect, useRef, useState } from 'react'
import { JOB_AGENT } from '../constants'
import { useChatSession } from '../hooks/useChatSession'
import Composer from './Composer'
import MessageList from './MessageList'

/** 在简历工作台右栏展示求职智能体，沿用聊天功能的会话与流式运行协议。 */
function JobChatPanel() {
  const chat = useChatSession()
  const initialized = useRef(false)
  const [draft, setDraft] = useState('')
  const jobConversations = chat.conversations.filter((item) => item.agent === JOB_AGENT)

  useEffect(() => {
    if (chat.sidebarLoading || initialized.current) return
    initialized.current = true
    const latest = chat.conversations.find((item) => item.agent === JOB_AGENT)
    if (latest) chat.selectConversation(latest.conversation_id)
    else chat.selectAgent(JOB_AGENT)
  }, [chat.sidebarLoading, chat.conversations, chat.selectAgent, chat.selectConversation])

  async function send() {
    const message = draft.trim()
    if (!message || chat.sending) return
    setDraft('')
    const sent = await chat.sendMessage(message)
    if (!sent) setDraft((current) => current || message)
  }

  return (
    <section className="resume-job-panel" aria-label="求职助手对话">
      <header className="resume-job-header">
        <div><p className="resume-editor-eyebrow">JOB ASSISTANT</p><h2>求职助手</h2><span>{chat.status}</span></div>
        <button type="button" className="resume-secondary-button" disabled={!initialized.current || chat.sending} onClick={() => { chat.selectAgent(JOB_AGENT); setDraft('') }}>新对话</button>
      </header>
      {jobConversations.length > 0 && (
        <label className="resume-job-history">
          <span>历史对话</span>
          <select value={chat.activeConversationId ?? ''} onChange={(event) => chat.selectConversation(event.target.value)} disabled={chat.sending}>
            <option value="" disabled>新对话</option>
            {jobConversations.map((item) => <option value={item.conversation_id} key={item.conversation_id}>{item.title || '未命名对话'}</option>)}
          </select>
        </label>
      )}
      <p className="resume-job-capability">当前可讨论求职目标、岗位要求与经历表达。暂不读取或修改左侧预览的简历。</p>
      {chat.sidebarLoading && <p className="resume-job-state" role="status">正在加载对话…</p>}
      {chat.sidebarError && <p className="resume-job-error" role="alert">{chat.sidebarError} <button type="button" onClick={() => { void chat.refreshConversations() }}>重试</button></p>}
      <div className="resume-job-messages">
        <MessageList
          messages={chat.messages}
          loading={chat.historyLoading}
          conversationId={chat.activeConversationId}
          agent={JOB_AGENT}
          pendingQuestion={chat.pendingQuestion}
          questionDisabled={chat.sending}
          onSubmitQuestion={(answers) => { void chat.resumeRun(answers) }}
        />
      </div>
      {chat.olderCursor && !chat.historyLoading && <button className="resume-job-older" type="button" disabled={chat.loadingOlder} onClick={() => { void chat.loadOlderMessages() }}>{chat.loadingOlder ? '正在加载…' : '查看更早消息'}</button>}
      {chat.error && <p className="resume-job-error" role="alert">{chat.error}</p>}
      <Composer
        value={draft}
        disabled={!initialized.current || Boolean(chat.pendingQuestion)}
        sending={chat.sending}
        onChange={setDraft}
        onSend={() => { void send() }}
        onCancel={() => { void chat.cancelRun() }}
        canCancel={chat.canCancel}
        supportsImageUpload={false}
        attachments={[]}
        onAddAttachments={() => {}}
        onRemoveAttachment={() => {}}
      />
    </section>
  )
}

export default JobChatPanel
