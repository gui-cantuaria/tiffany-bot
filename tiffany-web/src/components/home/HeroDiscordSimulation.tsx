"use client";

import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { cn } from "@/lib/utils";

export function HeroDiscordSimulation() {
  const [step, setStep] = useState(0);

  useEffect(() => {
    const timer = setInterval(() => {
      setStep((s) => (s + 1) % 3);
    }, 4000);
    return () => clearInterval(timer);
  }, []);

  return (
    <motion.div
      animate={{
        y: [0, -10, 0],
        rotateX: [0, 2, 0],
        rotateY: [0, -2, 0]
      }}
      transition={{
        duration: 6,
        repeat: Infinity,
        ease: "easeInOut"
      }}
      className="absolute inset-0 bg-[#313338] border border-white/10 rounded-2xl shadow-2xl flex flex-col font-sans overflow-hidden"
    >
      
      {/* Header */}
      <div className="h-12 border-b border-[#2B2D31] flex items-center px-4 bg-[#2B2D31]">
        <div className="flex gap-2">
          <div className="w-3 h-3 rounded-full bg-red-500" />
          <div className="w-3 h-3 rounded-full bg-yellow-500" />
          <div className="w-3 h-3 rounded-full bg-green-500" />
        </div>
        <div className="ml-4 text-xs font-bold text-zinc-400">Gaming Server</div>
      </div>

      <div className="flex flex-1 overflow-hidden">
        {/* Sidebar */}
        <div className="w-48 bg-[#2B2D31] p-3 flex flex-col gap-1 border-r border-[#1E1F22]">
          <div className="text-[10px] font-bold text-zinc-500 uppercase px-2 mb-1 mt-2">Text Channels</div>
          <div className={cn("px-2 py-1.5 rounded text-sm flex items-center gap-2", step === 0 ? "bg-[#404249] text-white" : "text-zinc-400")}>
            <span className="text-zinc-500 text-lg">#</span> general
          </div>
          <div className={cn("px-2 py-1.5 rounded text-sm flex items-center gap-2", step === 1 ? "bg-[#404249] text-white" : "text-zinc-400")}>
            <span className="text-zinc-500 text-lg">#</span> news
          </div>
          <div className={cn("px-2 py-1.5 rounded text-sm flex items-center gap-2", step === 2 ? "bg-[#404249] text-white" : "text-zinc-400")}>
            <span className="text-zinc-500 text-lg">#</span> offers
          </div>
          <div className="px-2 py-1.5 rounded text-sm flex items-center gap-2 text-zinc-400">
            <span className="text-zinc-500 text-lg">#</span> moderation-log
          </div>
        </div>

        {/* Main Content */}
        <div className="flex-1 bg-[#313338] p-4 flex flex-col justify-end relative">
          
          <AnimatePresence mode="wait">
            
            {step === 0 && (
              <motion.div key="step0" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.2 }} className="flex flex-col gap-4">
                <div className="flex gap-3">
                  <div className="w-10 h-10 rounded-full bg-emerald-500 shrink-0 flex items-center justify-center text-white font-bold">A</div>
                  <div>
                    <div className="text-white text-sm font-medium">Alex</div>
                    <div className="text-zinc-300 text-sm flex items-center gap-1.5 mt-0.5">
                      <span className="bg-white/10 px-1.5 rounded text-fuchsia-300 font-mono text-xs">/play</span>
                      lofi hip hop radio
                    </div>
                  </div>
                </div>
                <div className="flex gap-3">
                  <img src="/logo.svg" className="w-10 h-10 rounded-full bg-[#111214] p-1 shrink-0" alt="Tiffany" />
                  <div>
                    <div className="text-white text-sm font-medium flex items-center gap-2 mb-1">
                      Tiffany Bot <span className="bg-[#5865F2] text-[10px] font-bold px-1.5 py-0.5 rounded text-white flex items-center gap-1">APP</span>
                    </div>
                    <div className="bg-[#2B2D31] border-l-4 border-fuchsia-500 p-3 rounded text-sm text-zinc-300">
                      <div className="text-white font-bold flex items-center gap-2 mb-1">
                        <span className="text-fuchsia-400">♫</span> Now Playing
                      </div>
                      <div className="text-white font-bold">Lofi Hip Hop Radio</div>
                      <div className="text-zinc-400 text-xs mb-3">24/7 Radio</div>
                      <div className="w-full border-t border-white/5 mb-3"></div>
                      <div className="text-xs font-mono text-zinc-500">00:00 ━━━━━━━━━ 42:18</div>
                    </div>
                  </div>
                </div>
              </motion.div>
            )}

            {step === 1 && (
              <motion.div key="step1" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.2 }} className="flex flex-col gap-4">
                <div className="flex gap-3">
                  <img src="/logo.svg" className="w-10 h-10 rounded-full bg-[#111214] p-1 shrink-0" alt="Tiffany" />
                  <div>
                    <div className="text-white text-sm font-medium flex items-center gap-2 mb-1">
                      Tiffany Bot <span className="bg-[#5865F2] text-[10px] px-1 rounded">APP</span>
                    </div>
                    <div className="bg-[#2B2D31] border-l-4 border-[var(--color-tiffany-primary)] p-3 rounded text-sm text-zinc-300">
                      <div className="font-bold text-white mb-1">Nova geração de chips promete revolucionar o mercado</div>
                      <div className="text-zinc-400 text-xs mb-2">A nova arquitetura traz melhorias significativas de performance...</div>
                      <span className="text-[10px] font-bold text-[var(--color-tiffany-primary)] uppercase">Tecnoblog</span>
                    </div>
                  </div>
                </div>
              </motion.div>
            )}

            {step === 2 && (
              <motion.div key="step2" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.2 }} className="flex flex-col gap-4">
                <div className="flex gap-3">
                  <img src="/logo.svg" className="w-10 h-10 rounded-full bg-[#111214] p-1 shrink-0" alt="Tiffany" />
                  <div>
                    <div className="text-white text-sm font-medium flex items-center gap-2 mb-1">
                      Tiffany Bot <span className="bg-[#5865F2] text-[10px] px-1 rounded">APP</span>
                    </div>
                    <div className="bg-[#2B2D31] border-l-4 border-amber-500 p-3 rounded text-sm text-zinc-300">
                      <div className="text-white font-bold mb-1">🔥 RTX 4060 Ti 8GB</div>
                      <div className="flex items-center gap-2">
                        <span className="text-emerald-400 font-bold">R$ 2.499</span>
                        <span className="text-zinc-500 line-through text-xs">R$ 3.199</span>
                      </div>
                    </div>
                  </div>
                </div>
              </motion.div>
            )}

          </AnimatePresence>
          
          <div className="mt-4 bg-[#383A40] rounded-lg p-2.5 flex items-center gap-2">
             <div className="w-6 h-6 rounded-full bg-white/10 flex items-center justify-center text-white/50">+</div>
             <div className="text-zinc-500 text-sm">Message #channel...</div>
          </div>
        </div>
      </div>
    </motion.div>
  );
}
