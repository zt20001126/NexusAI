import { useState } from 'react'
import type { FormEvent } from 'react'
import type { Question, QuestionAnswer } from '../api/agent'
import { MAX_QUESTION_SELECTION_COUNT } from '../constants'
import { selectCurrentQuestionAnswers } from '../model/currentQuestionAnswers.mjs'

interface AgentInteractionCardProps {
  questions: Question[]
  disabled: boolean
  embedded?: boolean
  onSubmit: (answers: Record<string, QuestionAnswer>) => void
}

/** 在对话流中展示统一追问题卡，并按当前批次收集必答内容。 */
function AgentInteractionCard({
  questions,
  disabled,
  embedded = false,
  onSubmit,
}: AgentInteractionCardProps) {
  const [answers, setAnswers] = useState<Record<string, QuestionAnswer>>({})

  function updateAnswer(questionId: string, value: QuestionAnswer) {
    setAnswers((current) => ({ ...current, [questionId]: value }))
  }

  function questionIsAnswered(question: Question): boolean {
    const answer = answers[question.id]
    if (question.type === 'SingleChoice') {
      return typeof answer === 'string'
        && question.options.some((option) => option.label === answer)
    }
    return Array.isArray(answer)
      && answer.length > 0
      && answer.every((label) => question.options.some((option) => option.label === label))
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!questions.every(questionIsAnswered)) return
    const answersForSubmission = Object.fromEntries(
      questions.map((question) => [question.id, answers[question.id] ?? '']),
    )
    onSubmit(selectCurrentQuestionAnswers(
      questions.map((question) => question.id),
      answersForSubmission,
    ))
  }

  return (
    <form
      className={`interaction-card${embedded ? ' interaction-card-message' : ''}`}
      onSubmit={handleSubmit}
    >
      <header className="interaction-heading">
        <div>
          <strong>需要补充信息</strong>
          <p>本轮共 {questions.length} 道必答题，回答后 NexusAI 会继续处理。</p>
        </div>
      </header>

      <div className="interaction-questions">
        {questions.map((question, index) => (
          <QuestionInput
            key={question.id}
            question={question}
            index={index}
            total={questions.length}
            value={answers[question.id] ?? ''}
            disabled={disabled}
            onChange={(value) => updateAnswer(question.id, value)}
          />
        ))}
      </div>

      <button
        className="interaction-submit"
        type="submit"
        disabled={disabled || questions.some((question) => !questionIsAnswered(question))}
      >
        {disabled ? '正在继续…' : '提交回答'} <span aria-hidden="true">→</span>
      </button>
    </form>
  )
}

interface QuestionInputProps {
  question: Question
  index: number
  total: number
  value: QuestionAnswer
  disabled: boolean
  onChange: (value: QuestionAnswer) => void
}

/** 显示统一的问题标题、选项说明和单选/多选控件。 */
function QuestionInput({
  question,
  index,
  total,
  value,
  disabled,
  onChange,
}: QuestionInputProps) {
  const selectedOptions = Array.isArray(value) ? value : []

  return (
    <fieldset className="interaction-field">
      <legend>
        <span className="interaction-question-index">问题 {index + 1} / {total}</span>
        <span className="interaction-question-title">{question.title}</span>
        <span className="interaction-required">必答</span>
      </legend>

      {question.type === 'SingleChoice' ? (
        <div className="interaction-options" role="radiogroup" aria-label={question.title}>
          {question.options.map((option) => (
            <label className="interaction-option" key={option.label}>
              <input
                type="radio"
                name={question.id}
                value={option.label}
                checked={value === option.label}
                onChange={() => onChange(option.label)}
                disabled={disabled}
              />
              <span className="interaction-option-content">
                <span>{option.label}</span>
                <small className="interaction-option-description">
                  {option.description}
                </small>
              </span>
            </label>
          ))}
        </div>
      ) : (
        <div className="interaction-options" aria-label={question.title}>
          {question.options.map((option) => (
            <label className="interaction-option" key={option.label}>
              <input
                type="checkbox"
                checked={selectedOptions.includes(option.label)}
                onChange={(event) => onChange(event.target.checked
                  ? [...selectedOptions, option.label]
                  : selectedOptions.filter((item) => item !== option.label))}
                disabled={disabled || (!selectedOptions.includes(option.label)
                  && selectedOptions.length >= MAX_QUESTION_SELECTION_COUNT)}
              />
              <span className="interaction-option-content">
                <span>{option.label}</span>
                <small className="interaction-option-description">
                  {option.description}
                </small>
              </span>
            </label>
          ))}
          <small className="interaction-hint">
            最多选择 {MAX_QUESTION_SELECTION_COUNT} 项
          </small>
        </div>
      )}
    </fieldset>
  )
}

export default AgentInteractionCard
