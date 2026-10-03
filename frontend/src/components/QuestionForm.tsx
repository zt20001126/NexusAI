import { useState } from 'react'
import type { FormEvent } from 'react'
import type { Question } from '../api/agent'

interface QuestionFormProps {
  questions: Question[]
  disabled: boolean
  onSubmit: (answers: Record<string, string>) => void
}

/** 展示 Agent 的结构化追问并收集恢复运行所需的答案。 */
function QuestionForm({ questions, disabled, onSubmit }: QuestionFormProps) {
  const [answers, setAnswers] = useState<Record<string, string>>({})

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (questions.every((question) => answers[question.id]?.trim())) onSubmit(answers)
  }

  return (
    <form className="question-card" onSubmit={handleSubmit}>
      <div className="question-heading">
        <span className="question-mark">?</span>
        <div>
          <strong>再补充一点信息</strong>
          <p>回答后，NexusAI 会接着处理。</p>
        </div>
      </div>
      {questions.map((question) => (
        <label className="question-field" key={question.id}>
          <span>{question.title}</span>
          <small>{question.prompt}</small>
          <textarea
            value={answers[question.id] ?? ''}
            onChange={(event) => setAnswers((current) => ({ ...current, [question.id]: event.target.value }))}
            placeholder="输入你的回答…"
            rows={2}
            disabled={disabled}
          />
        </label>
      ))}
      <button
        className="question-submit"
        type="submit"
        disabled={disabled || questions.some((question) => !answers[question.id]?.trim())}
      >
        {disabled ? '正在继续…' : '提交回答'} <span aria-hidden="true">→</span>
      </button>
    </form>
  )
}

export default QuestionForm
