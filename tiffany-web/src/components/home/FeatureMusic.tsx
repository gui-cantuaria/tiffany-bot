"use client";

import { motion } from "framer-motion";
import { Music, PlayCircle, FastForward, Repeat, ListMusic, CheckCircle, Volume2, RefreshCw } from "lucide-react";
import { cn } from "@/lib/utils";

export function FeatureMusic() {
  return (
    <section className="w-full max-w-[1200px] mx-auto mb-40">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-16 items-center">
        
        {/* Text side */}
        <motion.div
          initial={{ opacity: 0, x: -30 }}
          whileInView={{ opacity: 1, x: 0 }}
          viewport={{ once: true, margin: "-100px" }}
          transition={{ duration: 0.6, ease: "easeOut" }}
        >
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-fuchsia-500/10 border border-fuchsia-500/20 text-fuchsia-500 text-sm font-medium mb-6">
            <Music className="w-4 h-4" />
            <span>High-Fidelity Audio</span>
          </div>
          <h2 className="text-4xl md:text-5xl font-medium tracking-tight mb-6">
            Music that never stops.
          </h2>
          <p className="text-lg text-[var(--color-tiffany-text-secondary)] mb-8">
            Search. Queue. Play. Repeat.
          </p>
          
          <div className="grid grid-cols-3 gap-4">
            <div className="bg-white/[0.02] backdrop-blur-md border border-white/10 rounded-xl p-4 shadow-lg">
              <div className="text-xs text-zinc-500 font-bold uppercase mb-1">Queue</div>
              <div className="text-white font-medium text-lg flex items-center gap-2">
                12 tracks <ListMusic className="w-4 h-4 text-fuchsia-400" />
              </div>
            </div>
            <div className="bg-white/[0.02] backdrop-blur-md border border-white/10 rounded-xl p-4 shadow-lg">
              <div className="text-xs text-zinc-500 font-bold uppercase mb-1">24/7 Mode</div>
              <div className="text-emerald-400 font-medium text-lg flex items-center gap-2">
                ENABLED <RefreshCw className="w-4 h-4" />
              </div>
            </div>
            <div className="bg-white/[0.02] backdrop-blur-md border border-white/10 rounded-xl p-4 shadow-lg">
              <div className="text-xs text-zinc-500 font-bold uppercase mb-1">Volume</div>
              <div className="text-white font-medium text-lg flex items-center gap-2">
                80% <Volume2 className="w-4 h-4 text-fuchsia-400" />
              </div>
            </div>
          </div>
        </motion.div>
        
        {/* Visualization Side */}
        <motion.div 
          initial={{ opacity: 0, x: 30 }}
          whileInView={{ opacity: 1, x: 0 }}
          viewport={{ once: true, margin: "-100px" }}
          transition={{ duration: 0.6, ease: "easeOut", delay: 0.2 }}
          className="relative"
        >
          <div className="absolute inset-0 bg-gradient-to-tr from-fuchsia-500/20 to-transparent blur-3xl -z-10 rounded-full" />
          
          <div className="bg-[#313338] rounded-xl overflow-hidden border border-white/10 shadow-2xl">
            <div className="p-4 border-b border-[#2B2D31] text-xs font-bold text-zinc-400 uppercase tracking-widest flex justify-between items-center">
              <span># music</span>
            </div>
            
            {/* User Input Mockup */}
            <div className="p-4 border-b border-[#2B2D31] bg-[#2B2D31]/30">
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-full bg-emerald-500 flex items-center justify-center text-white font-bold text-sm shrink-0">A</div>
                <div>
                  <div className="text-white font-medium text-sm">Alex</div>
                  <div className="text-[#DBDEE1] text-sm flex items-center gap-1.5 mt-0.5">
                    <span className="bg-white/10 px-1.5 rounded text-fuchsia-300 font-mono text-xs">/play</span>
                    lofi hip hop radio
                  </div>
                </div>
              </div>
            </div>

            {/* Bot Response Mockup */}
            <div className="p-4 flex gap-3">
              <img src="/logo.svg" className="w-10 h-10 rounded-full bg-[#111214] p-1 shrink-0 mt-1" alt="Tiffany" />
              <div className="flex-1">
                <div className="text-white font-medium text-sm flex items-center gap-2 mb-1">
                    Tiffany Bot <span className="bg-[#5865F2] text-[10px] font-bold px-1.5 py-0.5 rounded text-white flex items-center gap-1"><CheckCircle className="w-3 h-3" /> APP</span>
                </div>
                
                <div className="bg-[#2B2D31] rounded-lg p-4 border-l-4 border-fuchsia-500 mt-2">
                  <div className="flex items-center gap-2 mb-3">
                    <Music className="w-4 h-4 text-fuchsia-400" />
                    <span className="text-white font-bold text-sm">NOW PLAYING</span>
                  </div>
                  <div className="text-white font-bold text-lg mb-1">Lofi Hip Hop Radio</div>
                  <div className="text-zinc-400 text-sm mb-4">♫ Lofi Girl • 24/7 Radio</div>
                  
                  <div className="flex items-center gap-3 text-xs font-mono text-zinc-500 mb-4">
                    <span>00:42</span>
                    <div className="flex-1 h-1.5 bg-[#1E1F22] rounded-full overflow-hidden">
                      <div className="w-[10%] h-full bg-fuchsia-500 rounded-full"></div>
                    </div>
                    <span>42:18</span>
                  </div>

                  <div className="flex gap-2">
                    <button className="bg-[#383A40] text-[#DBDEE1] px-4 py-2 rounded text-sm hover:bg-[#404249] transition-colors flex items-center gap-2">
                      <PlayCircle className="w-4 h-4" /> Pause
                    </button>
                    <button className="bg-[#383A40] text-[#DBDEE1] px-4 py-2 rounded text-sm hover:bg-[#404249] transition-colors flex items-center gap-2">
                      <Repeat className="w-4 h-4" /> Loop
                    </button>
                    <button className="bg-[#383A40] text-[#DBDEE1] px-4 py-2 rounded text-sm hover:bg-[#404249] transition-colors flex items-center gap-2">
                      <FastForward className="w-4 h-4" /> Skip
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </motion.div>

      </div>
    </section>
  );
}
