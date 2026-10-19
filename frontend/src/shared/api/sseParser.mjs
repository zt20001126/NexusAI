/** 将一段 SSE 文本解析为事件帧；支持 event/id 和多行 data。 */
export function parseSseBlock(block) {
  let id = null
  let event = null
  const dataLines = []

  for (const line of block.split(/\r?\n/)) {
    if (!line || line.startsWith(':')) continue
    const separator = line.indexOf(':')
    const field = separator === -1 ? line : line.slice(0, separator)
    const rawValue = separator === -1 ? '' : line.slice(separator + 1)
    const value = rawValue.startsWith(' ') ? rawValue.slice(1) : rawValue
    if (field === 'id' && !value.includes('\0')) id = value
    else if (field === 'event') event = value
    else if (field === 'data') dataLines.push(value)
  }

  return {
    id,
    event,
    data: dataLines.length > 0 ? JSON.parse(dataLines.join('\n')) : null,
  }
}
