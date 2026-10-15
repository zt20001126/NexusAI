/** 只保留当前追问批次的答案，避免前一批状态进入恢复请求。 */
export function selectCurrentQuestionAnswers(
  questionIds: string[],
  answers: Record<string, string>,
): Record<string, string>
