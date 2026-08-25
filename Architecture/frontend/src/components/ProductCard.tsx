import type { ShoppingItem } from '../types'

const CATEGORY_COLORS: Record<string, string> = {
  furniture: 'bg-amber-100 text-amber-700 dark:bg-amber-900 dark:text-amber-300',
  lighting:  'bg-yellow-100 text-yellow-700 dark:bg-yellow-900 dark:text-yellow-300',
  flooring:  'bg-stone-100 text-stone-700 dark:bg-stone-900 dark:text-stone-300',
  fixtures:  'bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300',
  decor:     'bg-pink-100 text-pink-700 dark:bg-pink-900 dark:text-pink-300',
}

export default function ProductCard({ item }: { item: ShoppingItem }) {
  const badge = CATEGORY_COLORS[item.category] ?? 'bg-gray-100 text-gray-700'
  return (
    <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-700 p-4 flex flex-col gap-3 shadow-sm">
      <div className="flex items-start justify-between gap-2">
        <h4 className="font-medium text-gray-900 dark:text-white text-sm">{item.name}</h4>
        <span className={`text-xs px-2 py-0.5 rounded-full shrink-0 font-medium ${badge}`}>
          {item.category}
        </span>
      </div>
      <p className="text-xs text-gray-500 dark:text-gray-400 flex-1">{item.description}</p>
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold text-orange-600 dark:text-orange-400">
          {item.price_range_lkr}
        </span>
        <button className="text-xs text-gray-500 dark:text-gray-400 border border-gray-200 dark:border-gray-700 px-3 py-1 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors">
          Find Product
        </button>
      </div>
    </div>
  )
}
