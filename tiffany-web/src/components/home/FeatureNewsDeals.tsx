"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { Newspaper, Rss, ArrowRight, CheckCircle, Store, Link as LinkIcon, Settings2 } from "lucide-react";
import { cn } from "@/lib/utils";

export function FeatureNews() {
  return (
    <section className="w-full max-w-[1200px] mx-auto mb-40">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-16 items-center">
        
        {/* Text / Config side */}
        <motion.div
          initial={{ opacity: 0, x: -30 }}
          whileInView={{ opacity: 1, x: 0 }}
          viewport={{ once: true, margin: "-100px" }}
          transition={{ duration: 0.6, ease: "easeOut" }}
        >
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-[var(--color-tiffany-primary)]/10 border border-[var(--color-tiffany-primary)]/20 text-[var(--color-tiffany-primary)] text-sm font-medium mb-6">
            <Newspaper className="w-4 h-4" />
            <span>Automated News Pipeline</span>
          </div>
          <h2 className="text-4xl md:text-5xl font-medium tracking-tight mb-6">
            Your sources.<br/>Your channels.
          </h2>
          <p className="text-lg text-[var(--color-tiffany-text-secondary)] mb-8">
            Tiffany automatically turns your chosen sources into ready-to-post Discord messages.
          </p>
          
          <div className="bg-white/[0.02] backdrop-blur-xl border border-white/10 rounded-2xl p-6 shadow-xl">
            <div className="text-sm font-bold text-zinc-500 uppercase tracking-wider mb-4">Configuration Example</div>
            
            <div className="space-y-4">
              <div>
                <div className="text-xs text-zinc-400 mb-1">Select Sources</div>
                <div className="flex flex-wrap gap-2">
                  {["Tecnoblog", "Canaltech", "The Verge", "IGN", "Custom RSS"].map((src, i) => (
                    <div key={src} className={cn(
                      "px-3 py-1.5 rounded-lg border text-sm font-medium flex items-center gap-2",
                      i < 2 ? "bg-[var(--color-tiffany-primary)]/20 border-[var(--color-tiffany-primary)]/30 text-white" : "bg-white/5 border-white/5 text-zinc-400"
                    )}>
                      {i < 2 && <CheckCircle className="w-3.5 h-3.5 text-[var(--color-tiffany-primary)]" />}
                      {src}
                    </div>
                  ))}
                </div>
              </div>
              
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <div className="text-xs text-zinc-400 mb-1">Destination</div>
                  <div className="bg-[#313338] px-3 py-2 rounded-lg text-sm text-white font-medium border border-white/5">
                    # tecnologia
                  </div>
                </div>
                <div>
                  <div className="text-xs text-zinc-400 mb-1">Format</div>
                  <div className="bg-[#313338] px-3 py-2 rounded-lg text-sm text-white font-medium border border-white/5 flex items-center gap-2">
                    <Settings2 className="w-4 h-4 text-zinc-400" /> Standard Embed
                  </div>
                </div>
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
          <div className="absolute inset-0 bg-gradient-to-tr from-[var(--color-tiffany-primary)]/20 to-transparent blur-3xl -z-10 rounded-full" />
          
          <div className="flex flex-col gap-4">
            {/* Source Flow */}
            <div className="flex items-center gap-4 justify-center text-zinc-500 mb-4">
               <div className="w-12 h-12 rounded-2xl bg-white/5 flex items-center justify-center border border-white/10"><Rss className="w-6 h-6" /></div>
               <ArrowRight className="w-5 h-5 animate-pulse" />
               <img src="/logo.svg" className="w-12 h-12 object-contain" alt="Tiffany" />
               <ArrowRight className="w-5 h-5 animate-pulse" />
               <div className="w-12 h-12 rounded-2xl bg-[#5865F2]/20 flex items-center justify-center border border-[#5865F2]/30"><span className="text-[#5865F2] font-bold text-xl">#</span></div>
            </div>

            {/* Discord Mock */}
            <div className="bg-[#313338] rounded-xl overflow-hidden border border-white/10 shadow-2xl">
              <div className="p-4 border-b border-[#2B2D31] text-xs font-bold text-zinc-400 uppercase tracking-widest">
                # tecnologia
              </div>
              <div className="p-4 flex gap-3">
                <img src="/logo.svg" className="w-10 h-10 rounded-full bg-[#111214] p-1 shrink-0" alt="Tiffany" />
                <div className="flex-1">
                  <div className="text-white font-medium text-sm flex items-center gap-2 mb-1">
                      Tiffany Bot <span className="bg-[#5865F2] text-[10px] font-bold px-1.5 py-0.5 rounded text-white flex items-center gap-1"><CheckCircle className="w-3 h-3" /> APP</span>
                  </div>
                  <div className="bg-[#2B2D31] rounded-lg overflow-hidden border-l-4 border-[var(--color-tiffany-primary)]">
                      <div className="h-32 bg-gray-800 bg-[url('https://images.unsplash.com/photo-1518770660439-4636190af475?q=80&w=1000')] bg-cover bg-center" />
                      <div className="p-3">
                        <div className="text-white font-bold text-sm mb-1">Nova geração de chips promete revolucionar o mercado</div>
                        <div className="text-zinc-400 text-xs mb-3 line-clamp-2">A arquitetura recém anunciada traz melhorias significativas de performance e eficiência energética para notebooks...</div>
                        <div className="flex items-center justify-between">
                          <span className="text-[10px] font-bold text-[var(--color-tiffany-primary)] uppercase">Tecnoblog</span>
                          <span className="text-[10px] text-zinc-500">Publicado há 5m</span>
                        </div>
                      </div>
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

export function FeatureDeals() {
  return (
    <section className="w-full max-w-[1200px] mx-auto mb-40">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-16 items-center">
        
        {/* Visualization Side */}
        <motion.div 
          initial={{ opacity: 0, x: -30 }}
          whileInView={{ opacity: 1, x: 0 }}
          viewport={{ once: true, margin: "-100px" }}
          transition={{ duration: 0.6, ease: "easeOut", delay: 0.2 }}
          className="order-2 lg:order-1 relative"
        >
          <div className="absolute inset-0 bg-gradient-to-tr from-amber-500/20 to-transparent blur-3xl -z-10 rounded-full" />
          
          <div className="bg-[#313338] rounded-xl overflow-hidden border border-white/10 shadow-2xl">
            <div className="p-4 border-b border-[#2B2D31] text-xs font-bold text-zinc-400 uppercase tracking-widest">
              # ofertas
            </div>
            <div className="p-4 flex gap-3">
              <img src="/logo.svg" className="w-10 h-10 rounded-full bg-[#111214] p-1 shrink-0" alt="Tiffany" />
              <div className="flex-1">
                <div className="text-white font-medium text-sm flex items-center gap-2 mb-1">
                    Tiffany Bot <span className="bg-[#5865F2] text-[10px] font-bold px-1.5 py-0.5 rounded text-white flex items-center gap-1"><CheckCircle className="w-3 h-3" /> APP</span>
                </div>
                <div className="bg-[#2B2D31] rounded-lg p-4 border-l-4 border-amber-500">
                    <div className="text-white font-bold text-base mb-2">🔥 Placa de Vídeo RTX 4060 Ti 8GB</div>
                    <div className="flex items-end gap-3 mb-4">
                      <span className="text-emerald-400 font-bold text-2xl">R$ 2.499</span>
                      <span className="text-zinc-500 line-through text-sm pb-1">R$ 3.199</span>
                      <span className="bg-red-500/20 text-red-400 px-2 py-1 rounded text-xs font-bold mb-1">-22%</span>
                    </div>
                    
                    <div className="flex gap-2">
                      <button className="flex-1 bg-[#5865F2] hover:bg-[#4752C4] text-white text-sm font-medium py-2.5 rounded transition-colors flex items-center justify-center gap-2">
                        <LinkIcon className="w-4 h-4" /> Comprar na Amazon
                      </button>
                    </div>
                </div>
              </div>
            </div>
          </div>
        </motion.div>

        {/* Text / Config side */}
        <motion.div 
          initial={{ opacity: 0, x: 30 }}
          whileInView={{ opacity: 1, x: 0 }}
          viewport={{ once: true, margin: "-100px" }}
          transition={{ duration: 0.6, ease: "easeOut" }}
          className="order-1 lg:order-2"
        >
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-amber-500/10 border border-amber-500/20 text-amber-500 text-sm font-medium mb-6">
            <Store className="w-4 h-4" />
            <span>Live Deals Channel</span>
          </div>
          <h2 className="text-4xl md:text-5xl font-medium tracking-tight mb-6">
            Deals, directly in Discord.
          </h2>
          <p className="text-lg text-[var(--color-tiffany-text-secondary)] mb-8">
            Connect your stores and let Tiffany turn offers into ready-to-post deals.
          </p>
          
          <div className="bg-white/[0.02] backdrop-blur-xl border border-white/10 rounded-2xl p-6 shadow-xl">
            <div className="space-y-2">
              {[
                { name: "Promobit", status: "Active" },
                { name: "Amazon", status: "Affiliate configured" },
                { name: "Mercado Livre", status: "Affiliate configured" },
                { name: "Shopee", status: "Affiliate configured" },
                { name: "AliExpress", status: "Affiliate configured" },
                { name: "Terabyte", status: "Affiliate configured" },
                { name: "Shopinfo", status: "Affiliate configured" },
              ].map((store, idx) => (
                <div key={store.name} className="flex items-center justify-between p-2.5 rounded-lg border border-white/5 bg-white/5 opacity-80">
                  <div className="flex items-center gap-3">
                    <div className="w-6 h-6 rounded bg-zinc-800 flex items-center justify-center">
                      <span className="text-white font-bold text-[10px]">{store.name.substring(0,2).toUpperCase()}</span>
                    </div>
                    <div>
                      <div className="text-sm font-medium text-white">{store.name}</div>
                    </div>
                  </div>
                  <div className="text-xs text-emerald-400 flex items-center gap-1">
                    <CheckCircle className="w-3 h-3" /> {store.status}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </motion.div>

      </div>
    </section>
  );
}
