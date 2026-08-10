import Link from "next/link";

export function Footer() {
  return (
    <footer className="w-full bg-[#050507] border-t border-white/5 pt-20 pb-10">
      <div className="max-w-[1200px] mx-auto px-6 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-12 lg:gap-8 mb-16">
        
        {/* Brand Column */}
        <div className="lg:col-span-2">
          <Link href="/" className="flex items-center gap-3 mb-6">
            <img src="/logo.svg" className="w-8 h-8 object-contain" alt="Tiffany Logo" />
            <span className="text-xl font-bold tracking-tight text-white">Tiffany Bot</span>
          </Link>
          <p className="text-zinc-500 text-sm max-w-sm leading-relaxed mb-6">
            One bot for the things your Discord does every day.
          </p>
          <div className="flex items-center gap-4">
            <a href="#" className="w-10 h-10 rounded-full bg-white/5 border border-white/10 flex items-center justify-center text-zinc-400 hover:text-white hover:bg-white/10 transition-colors">
              <svg viewBox="0 0 24 24" className="w-5 h-5" fill="currentColor">
                <path d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" />
              </svg>
            </a>
            <a href="#" className="w-10 h-10 rounded-full bg-white/5 border border-white/10 flex items-center justify-center text-zinc-400 hover:text-white hover:bg-white/10 transition-colors font-bold text-lg">
              <span className="mb-1">𝕏</span>
            </a>
          </div>
        </div>

        {/* Links */}
        <div>
          <h4 className="text-white font-semibold mb-6 uppercase tracking-wider text-xs">Product</h4>
          <ul className="space-y-4 text-sm text-zinc-500">
            <li><Link href="/commands" className="hover:text-white transition-colors">Commands</Link></li>
            <li><Link href="/pricing" className="hover:text-white transition-colors">Premium</Link></li>
            <li><Link href="/dashboard" className="hover:text-white transition-colors">Dashboard</Link></li>
            <li><a href="#" className="hover:text-white transition-colors">Documentation</a></li>
          </ul>
        </div>

        <div>
          <h4 className="text-white font-semibold mb-6 uppercase tracking-wider text-xs">Community</h4>
          <ul className="space-y-4 text-sm text-zinc-500">
            <li><a href="#" className="hover:text-white transition-colors">Support</a></li>
            <li><a href="#" className="hover:text-white transition-colors">Discord</a></li>
            <li><a href="#" className="hover:text-white transition-colors">X</a></li>
          </ul>
        </div>

        <div>
          <h4 className="text-white font-semibold mb-6 uppercase tracking-wider text-xs">Legal</h4>
          <ul className="space-y-4 text-sm text-zinc-500">
            <li><a href="#" className="hover:text-white transition-colors">Privacy Policy</a></li>
            <li><a href="#" className="hover:text-white transition-colors">Terms of Service</a></li>
            <li><a href="#" className="hover:text-white transition-colors">Affiliate Terms</a></li>
          </ul>
        </div>
      </div>

      <div className="max-w-[1200px] mx-auto px-6 pt-8 border-t border-white/5 flex flex-col md:flex-row items-center justify-between gap-4">
        <p className="text-zinc-600 text-xs">
          &copy; {new Date().getFullYear()} Tiffany Bot. All rights reserved.
        </p>
        <p className="text-zinc-600 text-xs flex items-center gap-1">
          Not affiliated with Discord Inc.
        </p>
      </div>
    </footer>
  );
}
