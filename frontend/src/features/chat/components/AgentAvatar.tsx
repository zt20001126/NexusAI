import { useMemo } from 'react'
import { Avatar, Style } from '@dicebear/core'
import bottts from '@dicebear/styles/bottts.json' with { type: 'json' }
import { AgentType } from '../constants'

const AGENT_AVATAR_SIZE = 128
const robotAvatarStyle = new Style(bottts)
const avatarSourceByAgent = new Map<AgentType, string>()

interface AgentAvatarProps {
  agent: AgentType
}

/** 保留旧头像生成所用的稳定 seed；它们仅用于视觉生成，不是 API 或数据库 ID。 */
const avatarSeedByAgent: Record<AgentType, string> = {
  [AgentType.COMMON]: '1874244142498832385',
  [AgentType.IMAGE]: '1874244142498832386',
  [AgentType.LISTING]: '1874244142498832387',
  [AgentType.RESEARCH]: '1874244142498832388',
  [AgentType.LABOR_LAW]: '1874244142498832389',
  [AgentType.LITERATURE_READER]: '1874244142498832390',
  [AgentType.BASIC_CONVERSATION]: '1874244142498832391',
}

/** 按稳定智能体类型生成对应的固定机器人头像，并在各聊天区域共用。 */
function AgentAvatar({ agent }: AgentAvatarProps) {
  const avatarSource = useMemo(
    () => {
      const cachedSource = avatarSourceByAgent.get(agent)
      if (cachedSource) return cachedSource

      const generatedSource = new Avatar(robotAvatarStyle, {
        seed: avatarSeedByAgent[agent],
        size: AGENT_AVATAR_SIZE,
      }).toDataUri()
      avatarSourceByAgent.set(agent, generatedSource)
      return generatedSource
    },
    [agent],
  )

  return <img className="agent-avatar-image" src={avatarSource} alt="" aria-hidden="true" draggable={false} />
}

export default AgentAvatar
