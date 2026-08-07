import { useEffect } from 'react'
import { EditorContent, useEditor } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'

// A deliberately small rich-text editor for Gap/Flush notes.
//
// Built on Tiptap's own packages with a hand-written toolbar rather than a
// batteries-included editor component, for the same reason this app has no
// UI component library anywhere else: a prebuilt editor arrives with its
// own design system and would look nothing like the rest of these pages.
// StarterKit already provides everything the toolbar below exposes.
//
// The HTML this produces is *not* trusted. It is sanitised server-side
// before storage (backend/app/core/html_sanitize.py) -- this component
// only decides what the user can conveniently type, not what is allowed
// to be saved.

// Each button and whether it is currently active, kept as data so the
// toolbar markup stays a single map rather than a dozen near-identical
// blocks.
const TOOLBAR = [
  { label: 'B', title: 'Bold', mark: 'bold', run: (c) => c.toggleBold() },
  { label: 'I', title: 'Italic', mark: 'italic', run: (c) => c.toggleItalic() },
  { label: 'S', title: 'Strikethrough', mark: 'strike', run: (c) => c.toggleStrike() },
  {
    label: 'H2',
    title: 'Heading',
    mark: 'heading',
    markArgs: { level: 2 },
    run: (c) => c.toggleHeading({ level: 2 }),
  },
  { label: '• List', title: 'Bulleted list', mark: 'bulletList', run: (c) => c.toggleBulletList() },
  { label: '1. List', title: 'Numbered list', mark: 'orderedList', run: (c) => c.toggleOrderedList() },
  { label: '❝', title: 'Quote', mark: 'blockquote', run: (c) => c.toggleBlockquote() },
]

function RichTextEditor({ value, onChange }) {
  const editor = useEditor({
    extensions: [StarterKit],
    content: value || '',
    onUpdate: ({ editor: instance }) => {
      // getHTML() returns "<p></p>" for an empty document; normalise that
      // to "" so an untouched editor doesn't count as content. The
      // backend does the same, but doing it here too keeps the value the
      // parent holds honest.
      const html = instance.getHTML()
      onChange(html === '<p></p>' ? '' : html)
    },
  })

  // Tiptap keeps its own copy of the document, so a `value` that changes
  // from outside (switching entry, or a refresh after save) has to be
  // pushed in explicitly. Guarded against the editor's own updates --
  // without the comparison this would fight the user's typing on every
  // keystroke and park the cursor at the start.
  useEffect(() => {
    if (!editor) return
    const incoming = value || ''
    const current = editor.getHTML() === '<p></p>' ? '' : editor.getHTML()
    if (incoming !== current) {
      editor.commands.setContent(incoming, { emitUpdate: false })
    }
  }, [editor, value])

  if (!editor) {
    return null
  }

  return (
    <div className="rich-text-editor">
      <div className="rich-text-toolbar">
        {TOOLBAR.map((button) => (
          <button
            key={button.label}
            type="button"
            title={button.title}
            // Without this the button steals focus from the document and
            // the selection the command is meant to act on is lost.
            onMouseDown={(e) => e.preventDefault()}
            className={editor.isActive(button.mark, button.markArgs) ? 'is-active' : undefined}
            onClick={() => button.run(editor.chain().focus()).run()}
          >
            {button.label}
          </button>
        ))}
        <span className="rich-text-toolbar-spacer" />
        <button
          type="button"
          title="Undo"
          onMouseDown={(e) => e.preventDefault()}
          onClick={() => editor.chain().focus().undo().run()}
        >
          ↶
        </button>
        <button
          type="button"
          title="Redo"
          onMouseDown={(e) => e.preventDefault()}
          onClick={() => editor.chain().focus().redo().run()}
        >
          ↷
        </button>
      </div>
      <EditorContent editor={editor} className="rich-text-content" />
    </div>
  )
}

export default RichTextEditor
