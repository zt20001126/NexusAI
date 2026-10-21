import { AgentType } from '../constants'
import RobotAvatar from '../../../shared/components/RobotAvatar'

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
  [AgentType.JOB]: '1874244142498832392',
}

/** 按智能体类型提供固定 seed，头像绘制器由共享界面能力复用。 */
function AgentAvatar({ agent }: AgentAvatarProps) {
  return <RobotAvatar seed={avatarSeedByAgent[agent]} />
}

export default AgentAvatar
