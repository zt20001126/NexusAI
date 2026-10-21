export type ResumeSectionIconName = 'profile' | 'education' | 'skills' | 'work' | 'projects' | 'style' | 'job'

interface ResumeSectionIconProps {
  name: ResumeSectionIconName
  className: string
}

function ResumeSectionIcon({ name, className }: ResumeSectionIconProps) {
  const commonProps = { fill: 'none', stroke: 'currentColor', strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const, strokeWidth: 1.6 }

  return (
    <svg className={className} viewBox="0 0 20 20" aria-hidden="true" focusable="false" {...commonProps}>
      {name === 'profile' && <><circle cx="10" cy="6.5" r="3" /><path d="M4.5 17c.4-3.1 2.3-4.7 5.5-4.7s5.1 1.6 5.5 4.7" /></>}
      {name === 'education' && <><path d="m2.5 7 7.5-4 7.5 4-7.5 4-7.5-4Z" /><path d="M5.5 9v4.2c2.7 2.2 6.3 2.2 9 0V9M17.5 7v5" /></>}
      {name === 'skills' && <path d="m10 2.5 2.2 4.6 5.1.7-3.7 3.6.9 5.1-4.5-2.4-4.5 2.4.9-5.1-3.7-3.6 5.1-.7L10 2.5Z" />}
      {name === 'work' && <><rect x="2.5" y="6" width="15" height="11" rx="1.8" /><path d="M7 6V4.5c0-.8.7-1.5 1.5-1.5h3c.8 0 1.5.7 1.5 1.5V6M2.5 10h15M8 10v2h4v-2" /></>}
      {name === 'projects' && <><path d="M2.5 5.5h6l1.7 1.8h7.3v8.2c0 1.1-.9 2-2 2H4.5c-1.1 0-2-.9-2-2V5.5Z" /><path d="M2.5 8h15" /></>}
      {name === 'style' && <><path d="M3 5h14M3 10h14M3 15h14" /><circle cx="7" cy="5" r="1.5" fill="currentColor" /><circle cx="13" cy="10" r="1.5" fill="currentColor" /><circle cx="9" cy="15" r="1.5" fill="currentColor" /></>}
      {name === 'job' && <><rect x="2.5" y="6" width="15" height="11" rx="2" /><path d="M7 6V4.5A1.5 1.5 0 0 1 8.5 3h3A1.5 1.5 0 0 1 13 4.5V6M2.5 10h15M8 10v2h4v-2" /></>}
    </svg>
  )
}

export default ResumeSectionIcon
