import type { ResumeStyleConfig } from '../model/types'

interface StyleSettingsEditorProps {
  value: ResumeStyleConfig
  disabled?: boolean
  onChange: (value: ResumeStyleConfig) => void
}

function StyleSettingsEditor({ value, disabled = false, onChange }: StyleSettingsEditorProps) {
  function change<K extends keyof ResumeStyleConfig>(field: K, nextValue: ResumeStyleConfig[K]) {
    onChange({ ...value, [field]: nextValue })
  }

  function changeMargin(field: keyof ResumeStyleConfig['page_margin_mm'], nextValue: number) {
    onChange({ ...value, page_margin_mm: { ...value.page_margin_mm, [field]: nextValue } })
  }

  return (
    <div className="resume-editor-section">
      <div className="resume-editor-section-heading">
        <div><p className="resume-editor-eyebrow">PAGE STYLE</p><h2>排版设置</h2><p>调整字体、间距和颜色，预览会同步更新。</p></div>
      </div>
      <div className="resume-editor-card resume-style-card">
        <div className="resume-form-grid">
          <label className="resume-field resume-field-span"><span>字体</span><select value={value.font_family} disabled={disabled} onChange={(event) => change('font_family', event.target.value as ResumeStyleConfig['font_family'])}><option value="wenquanyi_zenhei">文泉驿正黑</option><option value="arphic_ukai">文鼎 PL 中楷</option></select></label>
          <label className="resume-field"><span>字号（pt）</span><input type="number" min={8} max={14} value={value.font_size_pt} disabled={disabled} onChange={(event) => change('font_size_pt', Number(event.target.value))} /></label>
          <label className="resume-field"><span>行高</span><input type="number" min={1} max={2} step={0.1} value={value.line_height} disabled={disabled} onChange={(event) => change('line_height', Number(event.target.value))} /></label>
          <label className="resume-field"><span>段落间距（pt）</span><input type="number" min={0} max={12} value={value.paragraph_spacing_pt} disabled={disabled} onChange={(event) => change('paragraph_spacing_pt', Number(event.target.value))} /></label>
          <label className="resume-field"><span>模块间距（pt）</span><input type="number" min={4} max={24} value={value.section_spacing_pt} disabled={disabled} onChange={(event) => change('section_spacing_pt', Number(event.target.value))} /></label>
        </div>
      </div>

      <div className="resume-editor-card resume-style-card">
        <div className="resume-style-card-title"><strong>页面边距</strong><span>5–30 mm</span></div>
        <div className="resume-margin-grid">
          {(['top', 'right', 'bottom', 'left'] as const).map((side) => (
            <label className="resume-field" key={side}><span>{{ top: '上', right: '右', bottom: '下', left: '左' }[side]}（mm）</span><input type="number" min={5} max={30} value={value.page_margin_mm[side]} disabled={disabled} onChange={(event) => changeMargin(side, Number(event.target.value))} /></label>
          ))}
        </div>
      </div>

      <div className="resume-editor-card resume-style-card">
        <div className="resume-style-card-title"><strong>主题颜色</strong><span>HEX 色值</span></div>
        <div className="resume-color-grid">
          <label className="resume-field"><span>标题颜色</span><span className="resume-color-input"><input type="color" value={value.heading_color} disabled={disabled} onChange={(event) => change('heading_color', event.target.value)} /><input value={value.heading_color} maxLength={7} disabled={disabled} onChange={(event) => change('heading_color', event.target.value)} /></span></label>
          <label className="resume-field"><span>分隔线颜色</span><span className="resume-color-input"><input type="color" value={value.divider_color} disabled={disabled} onChange={(event) => change('divider_color', event.target.value)} /><input value={value.divider_color} maxLength={7} disabled={disabled} onChange={(event) => change('divider_color', event.target.value)} /></span></label>
          <label className="resume-field"><span>分隔线粗细（pt）</span><input type="number" min={0.5} max={3} step={0.5} value={value.divider_width_pt} disabled={disabled} onChange={(event) => change('divider_width_pt', Number(event.target.value))} /></label>
        </div>
      </div>
    </div>
  )
}

export default StyleSettingsEditor
