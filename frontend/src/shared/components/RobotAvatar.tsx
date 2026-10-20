import { useMemo } from 'react'
import { Avatar, Style } from '@dicebear/core'
import bottts from '@dicebear/styles/bottts.json' with { type: 'json' }

const ROBOT_AVATAR_SIZE = 128
export const RESUME_ASSISTANT_AVATAR_SEED = '1874244142498832392'
const robotAvatarStyle = new Style(bottts)
const avatarSourceBySeed = new Map<string, string>()

interface RobotAvatarProps {
  seed: string
}

/** 按稳定 seed 生成可复用的机器人头像。 */
function RobotAvatar({ seed }: RobotAvatarProps) {
  const avatarSource = useMemo(() => {
    const cachedSource = avatarSourceBySeed.get(seed)
    if (cachedSource) return cachedSource

    const generatedSource = new Avatar(robotAvatarStyle, {
      seed,
      size: ROBOT_AVATAR_SIZE,
    }).toDataUri()
    avatarSourceBySeed.set(seed, generatedSource)
    return generatedSource
  }, [seed])

  return <img className="agent-avatar-image" src={avatarSource} alt="" aria-hidden="true" draggable={false} />
}

export default RobotAvatar
