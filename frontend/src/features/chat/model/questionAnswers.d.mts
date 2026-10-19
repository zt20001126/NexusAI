/** 将追问答案映射为便于阅读的展示条目。 */
export function toDisplayQuestionAnswers(
  answers: Record<string, unknown>,
  questionTitles?: Record<string, string>,
): Array<{ questionId: string; title: string; values: string[] }>
