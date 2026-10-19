const LEGACY_QUESTION_TITLES = {
  frame_material: '拍框材质',
  length_positioning: '球拍长度',
  unstrung_weight_range: '未穿线重量范围',
  brand_display: '品牌展示',
  head_size: '拍面大小',
  stringing_status: '穿线状态',
  grip_size: '握把尺寸',
  player_level: '适用水平',
  included_accessories: '随拍配件',
}

/** 将追问答案映射为便于阅读的展示条目。 */
export function toDisplayQuestionAnswers(answers, questionTitles = {}) {
  if (!answers || typeof answers !== 'object' || Array.isArray(answers)) return []

  return Object.entries(answers).flatMap(([questionId, answer]) => {
    const values = (Array.isArray(answer) ? answer : [answer])
      .filter((value) => typeof value === 'string' && value.trim())
      .map((value) => value.trim())
    if (values.length === 0) return []

    const title = typeof questionTitles?.[questionId] === 'string'
      ? questionTitles[questionId].trim()
      : ''
    return [{
      questionId,
      title: title || LEGACY_QUESTION_TITLES[questionId] || formatQuestionId(questionId),
      values,
    }]
  })
}

function formatQuestionId(questionId) {
  return questionId
    .split('_')
    .filter(Boolean)
    .map((word) => `${word[0].toUpperCase()}${word.slice(1)}`)
    .join(' ')
}
