export default function PdfViewer({ url }: { url: string }) {
  return (
    <div className="w-full">
      <iframe
        src={url}
        className="w-full h-[600px] rounded-xl border border-gray-200 dark:border-gray-700"
        title="PDF Report"
      />
      <p className="mt-2 text-xs text-gray-500 dark:text-gray-400 text-center">
        If the PDF does not display,{' '}
        <a href={url} target="_blank" rel="noopener noreferrer" className="text-orange-500 underline">
          open it directly
        </a>.
      </p>
    </div>
  )
}
