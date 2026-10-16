import { useMemo } from 'react'
import { Avatar, Style } from '@dicebear/core'
import bottts from '@dicebear/styles/bottts.json' with { type: 'json' }

const AGENT_AVATAR_SIZE = 128
const robotAvatarStyle = new Style(bottts)
const avatarSourceByAgent = new Map<string, string>()

interface AgentAvatarProps {
  agentId: string
}

/** 按智能体 ID 生成固定的机器人头像；选择页和消息区共用同一映射。 */
function AgentAvatar({ agentId }: AgentAvatarProps) {
  const avatarSource = useMemo(
    () => {
      const cachedSource = avatarSourceByAgent.get(agentId)
      if (cachedSource) return cachedSource

      const generatedSource = new Avatar(robotAvatarStyle, {
        seed: agentId,
        size: AGENT_AVATAR_SIZE,
      }).toDataUri()
      avatarSourceByAgent.set(agentId, generatedSource)
      return generatedSource
    },
    [agentId],
  )

  return <img src={avatarSource} alt="" aria-hidden="true" draggable={false} />
}

export default AgentAvatar
