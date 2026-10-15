/** 只保留当前追问批次的文本或多选数组答案。 */
export function selectCurrentQuestionAnswers(questionIds, answers) {
  return Object.fromEntries(
    questionIds.map((questionId) => [questionId, answers[questionId] ?? '']),
  )
}
