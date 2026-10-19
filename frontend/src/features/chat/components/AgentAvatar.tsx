import { useMemo } from 'react'
import { Avatar, Style } from '@dicebear/core'
import bottts from '@dicebear/styles/bottts.json' with { type: 'json' }
import type { AgentType } from '../constants'

const AGENT_AVATAR_SIZE = 128
const robotAvatarStyle = new Style(bottts)
const avatarSourceByAgent = new Map<string, string>()

interface AgentAvatarProps {
  agent: AgentType
}

/** 按智能体枚举值生成固定机器人头像；选择页和消息区共用同一映射。 */
function AgentAvatar({ agent }: AgentAvatarProps) {
  const avatarSource = useMemo(
    () => {
      const cachedSource = avatarSourceByAgent.get(agent)
      if (cachedSource) return cachedSource

      const generatedSource = new Avatar(robotAvatarStyle, {
        seed: agent,
        size: AGENT_AVATAR_SIZE,
      }).toDataUri()
      avatarSourceByAgent.set(agent, generatedSource)
      return generatedSource
    },
    [agent],
  )

  return <img src={avatarSource} alt="" aria-hidden="true" draggable={false} />
}

export default AgentAvatar
