import type { Components } from 'react-markdown'

/** Custom renderers so markdown looks good without @tailwindcss/typography. */
export const mdComponents: Components = {
  h1: ({ children }) => <h1 className="text-base font-bold mt-3 mb-1 text-text-primary">{children}</h1>,
  h2: ({ children }) => <h2 className="text-sm font-bold mt-3 mb-1 text-text-primary">{children}</h2>,
  h3: ({ children }) => <h3 className="text-xs font-bold mt-2 mb-1 text-text-primary">{children}</h3>,
  p: ({ children }) => <p className="mb-2 leading-relaxed">{children}</p>,
  ul: ({ children }) => <ul className="list-disc pl-4 mb-2 space-y-0.5">{children}</ul>,
  ol: ({ children }) => <ol className="list-decimal pl-4 mb-2 space-y-0.5">{children}</ol>,
  li: ({ children }) => <li className="leading-relaxed">{children}</li>,
  code: ({ children, className }) => {
    const isBlock = className?.includes('language-')
    if (isBlock) {
      return <code className="block bg-surface-1 rounded p-2 font-mono text-text-secondary overflow-x-auto whitespace-pre">{children}</code>
    }
    return <code className="bg-surface-1 rounded px-1 py-0.5 font-mono text-text-secondary">{children}</code>
  },
  pre: ({ children }) => <pre className="mb-2">{children}</pre>,
  strong: ({ children }) => <strong className="font-bold text-text-primary">{children}</strong>,
  blockquote: ({ children }) => <blockquote className="border-l-2 border-accent pl-3 my-2 text-text-dim italic">{children}</blockquote>,
  hr: () => <hr className="border-border my-3" />,
}
