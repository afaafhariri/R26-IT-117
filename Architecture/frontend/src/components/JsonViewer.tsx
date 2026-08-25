import { useState } from 'react'

function stringify(data: unknown, indent = 2): string {
  return JSON.stringify(data, null, indent)
}

export default function JsonViewer({ data }: { data: object }) {
  const [copied, setCopied] = useState(false)
  const text = stringify(data)

  const copy = () => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  return (
    <div className="relative">
      <button
        onClick={copy}
        className="absolute top-3 right-3 text-xs px-3 py-1 bg-gray-700 text-gray-200 hover:bg-gray-600 rounded-md transition-colors"
      >
        {copied ? 'Copied!' : 'Copy'}
      </button>
      <pre className="bg-gray-900 text-green-400 text-xs rounded-xl p-4 overflow-auto max-h-96 leading-relaxed">
        {text}
      </pre>
    </div>
  )
}
