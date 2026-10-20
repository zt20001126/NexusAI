import { useEffect } from 'react'
import type { ReactNode } from 'react'
import { EditorContent, useEditor } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import type { TiptapDocument } from '../model/types'

const richExtensions = [StarterKit.configure({
  blockquote: false,
  code: false,
  codeBlock: false,
  dropcursor: false,
  gapcursor: false,
  heading: false,
  horizontalRule: false,
  link: false,
  strike: false,
  trailingNode: false,
})]

const plainTextExtensions = [StarterKit.configure({
  blockquote: false,
  bold: false,
  bulletList: false,
  code: false,
  codeBlock: false,
  dropcursor: false,
  gapcursor: false,
  hardBreak: false,
  heading: false,
  horizontalRule: false,
  italic: false,
  link: false,
  listItem: false,
  listKeymap: false,
  orderedList: false,
  strike: false,
  trailingNode: false,
  underline: false,
  undoRedo: false,
})]

type RichEditorProps = {
  mode: 'rich'
  value: TiptapDocument
  disabled?: boolean
  onChange: (value: TiptapDocument) => void
}

type PlainEditorProps = {
  mode: 'plain'
  value: string
  disabled?: boolean
  onChange: (value: string) => void
}

type RichTextEditorProps = RichEditorProps | PlainEditorProps

function RichTextEditor(props: RichTextEditorProps) {
  const { mode, disabled = false } = props
  const editor = useEditor({
    extensions: mode === 'plain' ? plainTextExtensions : richExtensions,
    content: mode === 'plain' ? textToDocument(props.value) : props.value,
    editable: !disabled,
    immediatelyRender: true,
    editorProps: {
      attributes: {
        class: `resume-tiptap-content ${mode === 'plain' ? 'is-plain' : ''}`,
        'aria-label': mode === 'plain' ? '专业技能段落' : '经历描述',
      },
      handleKeyDown: (_view, event) => mode === 'plain' && event.key === 'Enter',
      handlePaste: (view, event) => {
        if (mode !== 'plain') return false
        const text = event.clipboardData?.getData('text/plain')
        if (text === undefined) return false
        event.preventDefault()
        view.dispatch(view.state.tr.insertText(text.replace(/[\r\n]+/g, ' ')))
        return true
      },
    },
    onUpdate: ({ editor: currentEditor }) => {
      if (props.mode === 'plain') {
        props.onChange(currentEditor.getText().replace(/[\r\n]+/g, ' '))
      } else {
        props.onChange(currentEditor.getJSON() as TiptapDocument)
      }
    },
  })

  useEffect(() => {
    if (!editor) return
    editor.setEditable(!disabled)
  }, [disabled, editor])

  useEffect(() => {
    if (!editor) return
    const nextContent = mode === 'plain' ? textToDocument(props.value) : props.value
    const currentContent = editor.getJSON()
    if (JSON.stringify(currentContent) !== JSON.stringify(nextContent)) {
      editor.commands.setContent(nextContent, { emitUpdate: false })
    }
  }, [editor, mode, props.value])

  if (!editor) return <div className="resume-tiptap-loading" aria-hidden="true" />

  if (mode === 'plain') {
    return (
      <div className="resume-tiptap-shell is-plain">
        <EditorContent editor={editor} />
        <span className="resume-plain-editor-hint">单条技能，一段文字</span>
      </div>
    )
  }

  return (
    <div className="resume-tiptap-shell">
      <div className="resume-tiptap-toolbar" role="toolbar" aria-label="经历内容格式">
        <ToolbarButton label="加粗" active={editor.isActive('bold')} disabled={disabled || !editor.can().chain().focus().toggleBold().run()} onClick={() => editor.chain().focus().toggleBold().run()}>
          <strong>B</strong>
        </ToolbarButton>
        <ToolbarButton label="斜体" active={editor.isActive('italic')} disabled={disabled || !editor.can().chain().focus().toggleItalic().run()} onClick={() => editor.chain().focus().toggleItalic().run()}>
          <em>I</em>
        </ToolbarButton>
        <ToolbarButton label="下划线" active={editor.isActive('underline')} disabled={disabled || !editor.can().chain().focus().toggleUnderline().run()} onClick={() => editor.chain().focus().toggleUnderline().run()}>
          <span className="resume-underline-label">U</span>
        </ToolbarButton>
        <span className="resume-toolbar-divider" aria-hidden="true" />
        <ToolbarButton label="无序列表" active={editor.isActive('bulletList')} disabled={disabled || !editor.can().chain().focus().toggleBulletList().run()} onClick={() => editor.chain().focus().toggleBulletList().run()}>
          ☷
        </ToolbarButton>
        <ToolbarButton label="有序列表" active={editor.isActive('orderedList')} disabled={disabled || !editor.can().chain().focus().toggleOrderedList().run()} onClick={() => editor.chain().focus().toggleOrderedList().run()}>
          1.
        </ToolbarButton>
        <span className="resume-toolbar-divider" aria-hidden="true" />
        <ToolbarButton label="撤销" disabled={disabled || !editor.can().undo()} onClick={() => editor.chain().focus().undo().run()}>
          ↶
        </ToolbarButton>
        <ToolbarButton label="重做" disabled={disabled || !editor.can().redo()} onClick={() => editor.chain().focus().redo().run()}>
          ↷
        </ToolbarButton>
      </div>
      <EditorContent editor={editor} />
    </div>
  )
}

interface ToolbarButtonProps {
  label: string
  active?: boolean
  disabled: boolean
  onClick: () => void
  children: ReactNode
}

function ToolbarButton({ label, active = false, disabled, onClick, children }: ToolbarButtonProps) {
  return (
    <button
      className={`resume-toolbar-button ${active ? 'is-active' : ''}`}
      type="button"
      aria-label={label}
      aria-pressed={active}
      disabled={disabled}
      onMouseDown={(event) => event.preventDefault()}
      onClick={onClick}
    >
      {children}
    </button>
  )
}

function textToDocument(value: string): TiptapDocument {
  return {
    type: 'doc',
    content: [{ type: 'paragraph', content: value ? [{ type: 'text', text: value }] : [] }],
  }
}

export default RichTextEditor
