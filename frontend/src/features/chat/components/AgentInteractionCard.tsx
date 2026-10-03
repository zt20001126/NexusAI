import { useState } from 'react'
import type { ChangeEvent, FormEvent } from 'react'
import type { Question } from '../api/agent'

interface AgentInteractionCardProps {
  questions: Question[]
  disabled: boolean
  onSubmit: (answers: Record<string, string>) => void
}

/** 在对话流中渲染 Agent 追问，并按题型收集答案。 */
function AgentInteractionCard({ questions, disabled, onSubmit }: AgentInteractionCardProps) {
  const [answers, setAnswers] = useState<Record<string, string>>({})

  function updateAnswer(questionId: string, value: string) {
    setAnswers((current) => ({ ...current, [questionId]: value }))
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (questions.every((question) => answers[question.id]?.trim())) onSubmit(answers)
  }

  return (
    <form className="interaction-card" onSubmit={handleSubmit}>
      <header className="interaction-heading">
        <strong>需要补充信息</strong>
        <p>回答后，NexusAI 会接着处理。</p>
      </header>

      <div className="interaction-questions">
        {questions.map((question) => (
          <QuestionInput
            key={question.id}
            question={question}
            value={answers[question.id] ?? ''}
            disabled={disabled}
            onChange={(value) => updateAnswer(question.id, value)}
          />
        ))}
      </div>

      <button
        className="interaction-submit"
        type="submit"
        disabled={disabled || questions.some((question) => !answers[question.id]?.trim())}
      >
        {disabled ? '正在继续…' : '提交回答'} <span aria-hidden="true">→</span>
      </button>
    </form>
  )
}

interface QuestionInputProps {
  question: Question
  value: string
  disabled: boolean
  onChange: (value: string) => void
}

function QuestionInput({ question, value, disabled, onChange }: QuestionInputProps) {
  const options = question.type === 'SingleChoice' || question.type === 'MultiChoice'
    ? question.options
    : []

  function handleFilesChange(event: ChangeEvent<HTMLInputElement>) {
    onChange(Array.from(event.target.files ?? [], (file) => file.name).join(', '))
  }

  return (
    <fieldset className="interaction-field">
      <legend>{question.title}</legend>
      <p className="interaction-prompt">{question.prompt}</p>

      {question.type === 'SingleChoice' && (
        <div className="interaction-options">
          {options.map((option) => (
            <label className="interaction-option" key={option}>
              <input type="radio" name={question.id} value={option} checked={value === option} onChange={() => onChange(option)} disabled={disabled} />
              <span>{option}</span>
            </label>
          ))}
        </div>
      )}

      {question.type === 'MultiChoice' && (
        <div className="interaction-options">
          {options.map((option) => {
            const selected = value ? value.split('\n') : []
            return (
              <label className="interaction-option" key={option}>
                <input
                  type="checkbox"
                  checked={selected.includes(option)}
                  onChange={(event) => onChange(event.target.checked
                    ? [...selected, option].join('\n')
                    : selected.filter((item) => item !== option).join('\n'))}
                  disabled={disabled}
                />
                <span>{option}</span>
              </label>
            )
          })}
        </div>
      )}

      {question.type === 'Confirmation' && (
        <div className="interaction-options interaction-confirmation">
          {['确认', '取消'].map((option) => (
            <label className="interaction-option" key={option}>
              <input type="radio" name={question.id} value={option} checked={value === option} onChange={() => onChange(option)} disabled={disabled} />
              <span>{option}</span>
            </label>
          ))}
        </div>
      )}

      {question.type === 'FileUpload' && (
        <input className="interaction-file" type="file" accept={question.accept} multiple={question.multiple} onChange={handleFilesChange} disabled={disabled} />
      )}

      {(question.type === undefined || question.type === 'TextQuestion') && (
        <textarea
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder={question.placeholder ?? '输入你的回答…'}
          rows={2}
          disabled={disabled}
        />
      )}
    </fieldset>
  )
}

export default AgentInteractionCard
