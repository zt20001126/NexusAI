/** 只保留当前追问批次的答案，避免前一批状态进入恢复请求。 */
export function selectCurrentQuestionAnswers(questionIds, answers) {
  return Object.fromEntries(
    questionIds.map((questionId) => [questionId, answers[questionId] ?? '']),
  )
}
