module.exports = {
  content: [
    "./templates/**/*.html",
    "./**/templates/**/*.html",
    "./static/js/**/*.js",
  ],
  theme: { extend: {} },
  safelist: [
    // критичные классы для модалки — на случай, если сканер что-то пропустит
    'fixed','inset-0','grid','place-items-center','p-4','max-w-lg',
    'bg-white','rounded-2xl','shadow-xl','ring-1','ring-black/5',
    'bg-black/50','backdrop-blur-[1px]','opacity-100','transition-opacity','duration-150','z-40','z-50',
    'inline-grid','w-9','h-9','rounded-full','text-gray-500','hover:text-gray-700',
    'px-6','pt-6','pb-3','space-y-5','space-y-3','space-y-1',
    'w-full','rounded-xl','border-gray-300','focus:border-gray-900','focus:ring-gray-900',
    'bg-gray-900','text-white','hover:bg-gray-800',
    'h-px','bg-gray-200','text-xs','text-gray-500',
    'text-sm','font-medium','text-gray-700','gap-2','gap-3',
    // цвета провайдеров:
    'bg-[#0077FF]','hover:bg-[#0066d6]','bg-[#FC3F1D]','hover:bg-[#e33718]',
    // утилиты hidden/overflow:
    'hidden','overflow-hidden'
  ],
  plugins: [],
}
