import { AgentType } from '../../features/chat/constants'
import RobotAvatar from './RobotAvatar'

interface AgentAvatarProps {
  agent: AgentType
}

/** 按智能体类型提供固定图标，供首页和工作区共用。 */
const avatarSeedByAgent: Record<AgentType, string> = {
  [AgentType.COMMON]: '1874244142498832385',
  [AgentType.IMAGE]: '1874244142498832386',
  [AgentType.LISTING]: '1874244142498832387',
  [AgentType.RESEARCH]: '1874244142498832388',
  [AgentType.LABOR_LAW]: '1874244142498832389',
  [AgentType.LITERATURE_READER]: '1874244142498832390',
  [AgentType.BASIC_CONVERSATION]: '1874244142498832391',
  [AgentType.JOB]: '1874244142498832392',
}

export default function AgentAvatar({ agent }: AgentAvatarProps) {
  return <RobotAvatar seed={avatarSeedByAgent[agent]} />
}
