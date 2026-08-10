"use client";

import { useState, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { 
  Search, 
  Music, 
  Terminal, 
  Sparkles, 
  Shield, 
  Gift, 
  Layout, 
  Command as CmdIcon,
  ChevronRight,
  Copy,
  CheckCircle,
  PlayCircle,
  Crown
} from "lucide-react";
import Link from "next/link";
import { COMMANDS, CommandCategory, Command } from "@/data/commands";
import { cn } from "@/lib/utils";
import { DiscordSimulation } from "@/components/commands/DiscordSimulation";

const CATEGORY_ICONS: Record<CommandCategory, React.ElementType> = {
  "Music": Music,
  "AI & Fun": Sparkles,
  "Embeds": Layout,
  "Giveaways": Gift,
  "Utility": Shield,
};

export default function CommandsPage() {
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedCategory, setSelectedCategory] = useState<CommandCategory | "All">("All");
  const [selectedCommand, setSelectedCommand] = useState<Command | null>(null);
  const [copied, setCopied] = useState(false);

  const categories = ["All", ...Array.from(new Set(COMMANDS.map(c => c.category)))] as (CommandCategory | "All")[];

  const filteredCommands = useMemo(() => {
    return COMMANDS.filter((cmd) => {
      const matchesCategory = selectedCategory === "All" || cmd.category === selectedCategory;
      const searchLower = searchQuery.toLowerCase();
      const matchesSearch = 
        cmd.name.toLowerCase().includes(searchLower) || 
        cmd.description.toLowerCase().includes(searchLower) ||
        (cmd.subcommands && cmd.subcommands.some(sub => sub.name.toLowerCase().includes(searchLower)));
      
      return matchesCategory && matchesSearch;
    });
  }, [searchQuery, selectedCategory]);

  const handleCopy = (usage: string) => {
    navigator.clipboard.writeText(usage);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="min-h-screen bg-[#050507] text-white selection:bg-fuchsia-500/30">
      
      {/* Navigation */}
      <nav className="fixed top-0 w-full z-50 bg-[#050507]/80 backdrop-blur-xl border-b border-white/5">
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
          <Link href="/" className="flex items-center gap-3 group">
            <div className="w-8 h-8 flex items-center justify-center group-hover:scale-105 transition-transform">
              <img src="/logo.svg" className="w-8 h-8 object-contain" alt="Tiffany Logo" />
            </div>
            <span className="font-semibold text-lg tracking-tight">Tiffany Bot</span>
          </Link>
          <div className="flex items-center gap-6 text-sm font-medium text-zinc-400">
            <Link href="/" className="hover:text-white transition-colors">Home</Link>
            <Link href="/commands" className="text-white">Commands</Link>
            <a href="#" className="hover:text-white transition-colors">Premium</a>
            <a href="#" className="h-9 px-4 rounded-full bg-white/10 hover:bg-white/20 text-white flex items-center justify-center transition-all">
              Add to Discord
            </a>
          </div>
        </div>
      </nav>

      <main className="pt-32 pb-24">
        
        {/* Hero Section */}
        <div className="max-w-7xl mx-auto px-6 mb-24 text-center pt-10">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, ease: "easeOut" }}
          >
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-fuchsia-500/10 border border-fuchsia-500/20 text-fuchsia-400 text-sm font-medium mb-6">
              <CmdIcon className="w-4 h-4" />
              <span>Command Library</span>
            </div>
            <h1 className="text-4xl md:text-6xl font-bold tracking-tight mb-6">
              Everything Tiffany can do.
            </h1>
            <p className="text-lg md:text-xl text-zinc-400 max-w-2xl mx-auto mb-16">
              Music, intelligence, moderation, community tools, and automation together inside one Discord bot.
            </p>
            
            {/* Discord Mockup Interaction */}
            <div className="max-w-xl mx-auto">
              <div className="bg-[#313338] rounded-xl text-left shadow-2xl border border-white/5 overflow-hidden">
                <div className="p-4 border-b border-[#2B2D31]">
                  <div className="flex items-center gap-3">
                    <img src="/logo.svg" className="w-8 h-8 rounded-full bg-[#111214] p-1" alt="Tiffany Avatar" />
                    <div>
                      <div className="text-white font-medium text-sm flex items-center gap-2">
                        Tiffany Bot <span className="bg-[#5865F2] text-[10px] font-bold px-1.5 py-0.5 rounded text-white flex items-center gap-1"><CheckCircle className="w-3 h-3" /> APP</span>
                      </div>
                      <div className="text-[#B5BAC1] text-xs">Now playing...</div>
                    </div>
                  </div>
                  <div className="mt-3 bg-[#2B2D31] rounded-lg p-3 border-l-4 border-fuchsia-500">
                    <div className="text-[#DBDEE1] text-sm font-medium mb-1">lofi hip hop radio - beats to relax/study to</div>
                    <div className="flex items-center gap-2 text-[#80848E] text-xs font-mono">
                      <PlayCircle className="w-4 h-4 text-[#DBDEE1]" /> 00:00 ━━━━━━━━━━━━━━
                    </div>
                  </div>
                </div>
                <div className="p-4 bg-[#313338]">
                  <div className="bg-[#383A40] rounded-xl p-3 flex items-center gap-2">
                    <span className="text-[#80848E] font-bold">/</span>
                    <span className="text-[#DBDEE1] font-mono text-sm">play</span>
                    <span className="bg-[#111214]/50 text-[#DBDEE1] px-2 py-0.5 rounded text-xs font-mono">song: lofi hip hop</span>
                  </div>
                </div>
              </div>
            </div>
          </motion.div>
        </div>

        {/* Command Explorer */}
        <div className="max-w-7xl mx-auto px-6">
          <div className="bg-white/[0.02] backdrop-blur-2xl border border-white/5 rounded-3xl overflow-hidden shadow-[0_8px_32px_0_rgba(0,0,0,0.36)] flex flex-col md:flex-row min-h-[700px]">
            
            {/* LEFT: Sidebar / Categories */}
            <div className="w-full md:w-64 border-b md:border-b-0 md:border-r border-white/5 bg-[#08080C] p-4 flex flex-col">
              
              {/* Prefix Info */}
              <div className="mb-6 flex flex-col gap-2">
                <div className="text-xs font-bold text-zinc-500 uppercase tracking-wider">Supported Prefixes</div>
                <div className="flex gap-2">
                  <div className="bg-white/5 border border-white/10 rounded-md px-2 py-1 text-xs font-mono text-zinc-300">/ (Slash Commands)</div>
                </div>
              </div>

              {/* Search */}
              <div className="relative mb-6">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500" />
                <input 
                  type="text"
                  placeholder="Search commands..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="w-full bg-white/5 border border-white/5 rounded-xl py-2 pl-9 pr-4 text-sm text-white placeholder:text-zinc-500 focus:outline-none focus:border-fuchsia-500/50 transition-colors"
                />
              </div>

              {/* Categories */}
              <div className="flex md:flex-col gap-2 overflow-x-auto pb-4 md:pb-0 scrollbar-hide">
                {categories.map((category) => {
                  const Icon = category === "All" ? CmdIcon : CATEGORY_ICONS[category];
                  const isActive = selectedCategory === category;
                  const count = category === "All" ? COMMANDS.length : COMMANDS.filter(c => c.category === category).length;
                  
                  return (
                    <button
                      key={category}
                      onClick={() => setSelectedCategory(category)}
                      className={cn(
                        "flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all whitespace-nowrap",
                        isActive 
                          ? "bg-fuchsia-500/10 text-fuchsia-400 border border-fuchsia-500/20" 
                          : "text-zinc-400 hover:text-white hover:bg-white/5 border border-transparent"
                      )}
                    >
                      <Icon className="w-4 h-4" />
                      <span>{category}</span>
                      <span className="ml-auto text-xs bg-white/10 px-2 py-0.5 rounded-full opacity-60">
                        {count}
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>

            {/* CENTER: Command List (Discord Autocomplete Style) */}
            <div className="w-full md:w-80 border-b md:border-b-0 md:border-r border-white/5 bg-[#1E1F22] flex flex-col h-[400px] md:h-auto overflow-y-auto custom-scrollbar relative">
              
              {/* Discord-style Autocomplete Header */}
              <div className="sticky top-0 bg-[#1E1F22] z-10 px-4 py-3 border-b border-white/5 flex items-center justify-between">
                <div className="text-xs font-bold text-[#B5BAC1] uppercase">Commands Matching</div>
                <div className="text-xs font-bold text-fuchsia-400 bg-fuchsia-500/10 px-2 py-0.5 rounded">{filteredCommands.length}</div>
              </div>

              {filteredCommands.length === 0 ? (
                <div className="flex-1 flex flex-col items-center justify-center p-8 text-center">
                  <div className="w-12 h-12 rounded-full bg-white/5 flex items-center justify-center mb-4">
                    <Search className="w-5 h-5 text-[#B5BAC1]" />
                  </div>
                  <h3 className="text-[#DBDEE1] font-medium mb-1">No matches</h3>
                </div>
              ) : (
                <div className="p-2 space-y-1">
                  {filteredCommands.map((cmd) => (
                    <button
                      key={cmd.name}
                      onClick={() => setSelectedCommand(cmd)}
                      className={cn(
                        "w-full flex items-center gap-3 p-2.5 rounded-md text-left transition-all group",
                        selectedCommand?.name === cmd.name
                          ? "bg-[#404249]" // Discord selected state
                          : "hover:bg-[#35373C]" // Discord hover state
                      )}
                    >
                      <div className="w-8 h-8 rounded-md bg-[#2B2D31] flex items-center justify-center shrink-0">
                        {/* Dynamic Icon based on category */}
                        {cmd.category === "Music" && <Music className="w-4 h-4 text-[#DBDEE1]" />}
                        {cmd.category === "AI & Fun" && <Sparkles className="w-4 h-4 text-[#DBDEE1]" />}
                        {cmd.category === "Utility" && <Shield className="w-4 h-4 text-[#DBDEE1]" />}
                        {cmd.category === "Giveaways" && <Gift className="w-4 h-4 text-[#DBDEE1]" />}
                        {cmd.category === "Embeds" && <Layout className="w-4 h-4 text-[#DBDEE1]" />}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className={cn(
                            "font-bold text-sm truncate",
                            selectedCommand?.name === cmd.name ? "text-white" : "text-[#DBDEE1]"
                          )}>
                            {cmd.name}
                          </span>
                          {cmd.premium && (
                            <Crown className="w-3 h-3 text-amber-400 shrink-0" />
                          )}
                        </div>
                        <p className="text-xs text-[#B5BAC1] truncate">
                          {cmd.description}
                        </p>
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </div>

            {/* RIGHT: Detail View & Interactive Sandbox */}
            <div className="flex-1 bg-[#050507] p-6 md:p-10 flex flex-col overflow-y-auto custom-scrollbar relative">
              {/* Background Glow */}
              <div className="absolute top-0 right-0 w-[500px] h-[500px] bg-fuchsia-500/5 blur-[150px] pointer-events-none rounded-full" />
              
              <AnimatePresence mode="wait">
                {selectedCommand ? (
                  <motion.div
                    key={selectedCommand.name}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -10 }}
                    transition={{ duration: 0.3 }}
                    className="max-w-2xl w-full relative z-10"
                  >
                    {/* Header Info */}
                    <div className="mb-10">
                      <div className="flex items-center gap-3 mb-3">
                        <h2 className="text-4xl font-mono font-bold text-white tracking-tight">
                          {selectedCommand.name}
                        </h2>
                        {selectedCommand.premium && (
                          <span className="flex items-center gap-1 px-2.5 py-1 rounded-md bg-amber-500/10 border border-amber-500/20 text-amber-400 text-xs font-bold uppercase tracking-wider">
                            <Crown className="w-3 h-3" /> Premium
                          </span>
                        )}
                        <span className="px-2.5 py-1 rounded-md bg-white/5 border border-white/10 text-zinc-300 text-xs font-bold uppercase tracking-wider">
                          {selectedCommand.category}
                        </span>
                      </div>
                      <p className="text-zinc-400 text-lg">
                        {selectedCommand.description}
                      </p>
                    </div>

                    {/* INTERACTIVE MOCKUP SANDBOX */}
                    <div className="mb-10">
                      <h3 className="text-xs font-bold text-zinc-500 uppercase tracking-wider mb-4 flex items-center gap-2">
                        <PlayCircle className="w-4 h-4" /> Live Preview
                      </h3>
                      <DiscordSimulation command={selectedCommand} />
                    </div>

                    {/* Command Details Grid */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                      {/* Usage */}
                      <div className="bg-white/5 border border-white/5 rounded-2xl p-5">
                        <h3 className="text-xs font-bold text-zinc-500 uppercase tracking-wider mb-3">Syntax</h3>
                        <div className="group relative bg-[#050507] rounded-lg p-3 flex items-center justify-between font-mono text-sm text-fuchsia-300">
                          <code>{selectedCommand.usage}</code>
                          <button 
                            onClick={() => handleCopy(selectedCommand.usage)}
                            className="text-zinc-500 hover:text-white transition-colors"
                          >
                            {copied ? <CheckCircle className="w-4 h-4 text-emerald-400" /> : <Copy className="w-4 h-4" />}
                          </button>
                        </div>
                      </div>

                      {/* Permissions */}
                      {selectedCommand.permissions && (
                        <div className="bg-white/5 border border-white/5 rounded-2xl p-5">
                          <h3 className="text-xs font-bold text-zinc-500 uppercase tracking-wider mb-3">Permissions</h3>
                          <div className="flex items-center gap-2">
                            <Shield className="w-4 h-4 text-amber-500" />
                            <span className="text-sm text-zinc-300">{selectedCommand.permissions}</span>
                          </div>
                        </div>
                      )}
                    </div>

                    {/* Subcommands List */}
                    {selectedCommand.subcommands && selectedCommand.subcommands.length > 0 && (
                      <div className="mt-8">
                        <h3 className="text-xs font-bold text-zinc-500 uppercase tracking-wider mb-4">Subcommands</h3>
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                          {selectedCommand.subcommands.map((sub) => (
                            <div key={sub.name} className="bg-white/5 border border-white/5 hover:border-white/10 transition-colors rounded-xl p-4">
                              <div className="font-mono text-sm text-fuchsia-300 mb-1">{selectedCommand.name} {sub.name}</div>
                              <div className="text-xs text-zinc-400">{sub.description}</div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                  </motion.div>
                ) : (
                  <motion.div
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    className="flex-1 flex flex-col items-center justify-center text-center max-w-sm mx-auto h-full"
                  >
                    <div className="w-20 h-20 rounded-3xl bg-white/5 flex items-center justify-center mb-6 relative">
                      <Terminal className="w-10 h-10 text-zinc-600" />
                      <div className="absolute -bottom-2 -right-2 w-8 h-8 rounded-full bg-fuchsia-500 flex items-center justify-center shadow-lg shadow-fuchsia-500/20">
                        <CmdIcon className="w-4 h-4 text-white" />
                      </div>
                    </div>
                    <h2 className="text-2xl font-semibold text-white mb-3">Select a command</h2>
                    <p className="text-zinc-500 leading-relaxed">
                      Explore the interactive command palette on the left to see live previews and syntax details.
                    </p>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-white/10 bg-[#050507] py-12 text-center text-zinc-500 text-sm">
        <p>&copy; {new Date().getFullYear()} Tiffany Bot. All rights reserved.</p>
      </footer>
    </div>
  );
}
