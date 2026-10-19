import { useState } from 'react'
import type { FormEvent } from 'react'
import type { Question, QuestionAnswer, QuestionOptionValue } from '../api/agent'
import {
  MAX_QUESTION_ANSWER_CHARS,
  MAX_QUESTION_SELECTION_CHARS,
  MAX_QUESTION_SELECTION_COUNT,
} from '../constants'
import { selectCurrentQuestionAnswers } from '../model/currentQuestionAnswers.mjs'

function getOptionLabel(option: QuestionOptionValue): string {
  return typeof option === 'string' ? option : option.label
}

function getOptionDescription(option: QuestionOptionValue): string | undefined {
  return typeof option === 'string' ? undefined : option.description
}

interface AgentInteractionCardProps {
  questions: Question[]
  questionRound: number
  maxQuestionRounds: number
  disabled: boolean
  embedded?: boolean
  onSubmit: (answers: Record<string, QuestionAnswer>) => void
}

/** 在对话流中展示规范化追问，并按当前批次收集必答内容。 */
function AgentInteractionCard({
  questions,
  questionRound,
  maxQuestionRounds,
  disabled,
  embedded = false,
  onSubmit,
}: AgentInteractionCardProps) {
  const [answers, setAnswers] = useState<Record<string, QuestionAnswer>>({})
  const [customAnswers, setCustomAnswers] = useState<Record<string, string>>({})
  const [customInputSelected, setCustomInputSelected] = useState<Record<string, boolean>>({})

  function updateAnswer(questionId: string, value: QuestionAnswer) {
    setAnswers((current) => ({ ...current, [questionId]: value }))
  }

  function updateCustomAnswer(questionId: string, value: string) {
    setCustomAnswers((current) => ({ ...current, [questionId]: value }))
  }

  function selectCustomInput(questionId: string, selected: boolean) {
    setCustomInputSelected((current) => ({ ...current, [questionId]: selected }))
  }

  function questionIsAnswered(question: Question): boolean {
    const answer = answers[question.id]
    if (question.type === 'SingleChoice') {
      return customInputSelected[question.id]
        ? Boolean(customAnswers[question.id]?.trim())
        : typeof answer === 'string'
          && question.options.some((option) => getOptionLabel(option) === answer)
    }
    if (question.type === 'MultiChoice') {
      const selectedOptions = Array.isArray(answer) ? answer : []
      return (selectedOptions.length > 0 || customInputSelected[question.id] === true)
        && (!customInputSelected[question.id] || Boolean(customAnswers[question.id]?.trim()))
    }
    if (question.type === 'Confirmation') {
      return answer === '确认' || answer === '取消'
    }
    return typeof answer === 'string' && Boolean(answer.trim())
  }

  function getSubmissionAnswer(question: Question): QuestionAnswer {
    const answer = answers[question.id] ?? ''
    if (question.type === 'SingleChoice' && customInputSelected[question.id]) {
      return customAnswers[question.id]?.trim() ?? ''
    }
    if (question.type === 'MultiChoice') {
      const selectedOptions = Array.isArray(answer) ? answer : []
      const customAnswer = customAnswers[question.id]?.trim()
      if (customInputSelected[question.id] && customAnswer && !selectedOptions.includes(customAnswer)) {
        return [...selectedOptions, customAnswer]
      }
      return selectedOptions
    }
    return answer
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!questions.every(questionIsAnswered)) return
    const answersForSubmission = Object.fromEntries(
      questions.map((question) => [question.id, getSubmissionAnswer(question)]),
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
        <span className="interaction-round-badge">第 {questionRound} / {maxQuestionRounds} 轮</span>
      </header>

      <div className="interaction-questions">
        {questions.map((question, index) => (
          <QuestionInput
            key={question.id}
            question={question}
            index={index}
            total={questions.length}
            value={answers[question.id] ?? ''}
            customValue={customAnswers[question.id] ?? ''}
            customSelected={customInputSelected[question.id] ?? false}
            disabled={disabled}
            onChange={(value) => updateAnswer(question.id, value)}
            onCustomChange={(value) => updateCustomAnswer(question.id, value)}
            onCustomSelectedChange={(selected) => selectCustomInput(question.id, selected)}
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
  customValue: string
  customSelected: boolean
  disabled: boolean
  onChange: (value: QuestionAnswer) => void
  onCustomChange: (value: string) => void
  onCustomSelectedChange: (selected: boolean) => void
}

/** 统一题号、必答状态、题型说明和题型控件。 */
function QuestionInput({
  question,
  index,
  total,
  value,
  customValue,
  customSelected,
  disabled,
  onChange,
  onCustomChange,
  onCustomSelectedChange,
}: QuestionInputProps) {
  const selectedOptions = Array.isArray(value) ? value : []
  const questionType = question.type ?? 'TextQuestion'
  const typeLabel = questionType === 'SingleChoice'
    ? '单选'
    : questionType === 'MultiChoice'
      ? '多选'
      : questionType === 'Confirmation'
        ? '确认'
        : '文本'

  return (
    <fieldset className="interaction-field">
      <legend>
        <span className="interaction-question-index">问题 {index + 1} / {total}</span>
        <span className="interaction-question-title">{question.title}</span>
        <span className="interaction-required">必答</span>
      </legend>
      <p className="interaction-prompt">
        <span className="interaction-question-type">{typeLabel}</span>
        {question.prompt}
      </p>

      {question.type === 'SingleChoice' && (
        <div className="interaction-options" role="radiogroup" aria-label={question.title}>
          {question.options.map((option) => {
            const label = getOptionLabel(option)
            const description = getOptionDescription(option)
            return (
              <label className="interaction-option" key={label}>
                <input
                  type="radio"
                  name={question.id}
                  value={label}
                  checked={!customSelected && value === label}
                  onChange={() => {
                    onCustomSelectedChange(false)
                    onChange(label)
                  }}
                  disabled={disabled}
                />
                <span className="interaction-option-content">
                  <span>{label}</span>
                  {description && (
                    <small className="interaction-option-description">
                      {description}
                    </small>
                  )}
                </span>
              </label>
            )
          })}
          {question.allow_custom_input && (
            <div className="interaction-custom-option">
              <label className="interaction-option">
                <input
                  type="radio"
                  name={question.id}
                  checked={customSelected}
                  onChange={() => {
                    onCustomSelectedChange(true)
                    onChange('')
                  }}
                  disabled={disabled}
                />
                <span>其他</span>
              </label>
              {customSelected && (
                <input
                  className="interaction-custom-input"
                  type="text"
                  value={customValue}
                  maxLength={MAX_QUESTION_ANSWER_CHARS}
                  placeholder="请输入其他内容"
                  onChange={(event) => onCustomChange(event.target.value)}
                  disabled={disabled}
                  aria-label={`${question.title}的其他答案`}
                />
              )}
            </div>
          )}
        </div>
      )}

      {question.type === 'MultiChoice' && (
        <div className="interaction-options" aria-label={question.title}>
          {question.options.map((option) => {
            const label = getOptionLabel(option)
            const description = getOptionDescription(option)
            return (
              <label className="interaction-option" key={label}>
                <input
                  type="checkbox"
                  checked={selectedOptions.includes(label)}
                  onChange={(event) => onChange(event.target.checked
                    ? [...selectedOptions, label]
                    : selectedOptions.filter((item) => item !== label))}
                  disabled={disabled || (!selectedOptions.includes(label)
                    && selectedOptions.length + (customSelected ? 1 : 0) >= MAX_QUESTION_SELECTION_COUNT)}
                />
                <span className="interaction-option-content">
                  <span>{label}</span>
                  {description && (
                    <small className="interaction-option-description">
                      {description}
                    </small>
                  )}
                </span>
              </label>
            )
          })}
          {question.allow_custom_input && (
            <div className="interaction-custom-option">
              <label className="interaction-option">
                <input
                  type="checkbox"
                  checked={customSelected}
                  onChange={(event) => onCustomSelectedChange(event.target.checked)}
                  disabled={disabled || (!customSelected
                    && selectedOptions.length >= MAX_QUESTION_SELECTION_COUNT)}
                />
                <span>其他</span>
              </label>
              {customSelected && (
                <input
                  className="interaction-custom-input"
                  type="text"
                  value={customValue}
                  maxLength={MAX_QUESTION_SELECTION_CHARS}
                  placeholder="请输入其他内容"
                  onChange={(event) => onCustomChange(event.target.value)}
                  disabled={disabled}
                  aria-label={`${question.title}的其他答案`}
                />
              )}
            </div>
          )}
          <small className="interaction-hint">最多选择 {MAX_QUESTION_SELECTION_COUNT} 项</small>
        </div>
      )}

      {question.type === 'Confirmation' && (
        <div className="interaction-options interaction-confirmation" role="radiogroup" aria-label={question.title}>
          {['确认', '取消'].map((option) => (
            <label className="interaction-option" key={option}>
              <input
                type="radio"
                name={question.id}
                value={option}
                checked={value === option}
                onChange={() => onChange(option)}
                disabled={disabled}
              />
              <span>{option}</span>
            </label>
          ))}
        </div>
      )}

      {(question.type === undefined || question.type === 'TextQuestion') && (
        <textarea
          value={typeof value === 'string' ? value : ''}
          onChange={(event) => onChange(event.target.value)}
          placeholder={question.placeholder ?? '输入你的回答…'}
          maxLength={MAX_QUESTION_ANSWER_CHARS}
          rows={2}
          disabled={disabled}
          aria-label={question.title}
          aria-required="true"
        />
      )}
    </fieldset>
  )
}

export default AgentInteractionCard
