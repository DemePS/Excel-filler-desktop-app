// ComptaIA's messages are Markdown: headings, lists, bold, tables, code. Rendered without raw HTML;
// links are shown, not followed (the window must not navigate away), and images show their text.

import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

export function Markdown({ text }: { text: string }) {
  return (
    <div className="md">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ children, href }) => <span className="md-link" title={href}>{children}</span>,
          img: ({ alt }) => <span>{alt}</span>,
          table: ({ children }) => <div className="md-table"><table>{children}</table></div>,
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  )
}
