/** 只保留当前追问批次的文本或多选数组答案。 */
export function selectCurrentQuestionAnswers(
  questionIds: string[],
  answers: Record<string, string | string[]>,
): Record<string, string | string[]>
