"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { CheckCircle, PlayCircle, ShieldAlert } from "lucide-react";
import { cn } from "@/lib/utils";

const CHANNELS = [
  { id: "music", name: "music" },
  { id: "ai", name: "ai-chat" },
  { id: "mod", name: "moderation-log" },
  { id: "news", name: "news" },
  { id: "deals", name: "deals" },
  { id: "games", name: "games" },
];

export function ProductExplorer() {
  const [activeChannel, setActiveChannel] = useState(CHANNELS[0].id);

  return (
    <div className="w-full max-w-[1000px] mx-auto bg-[#313338] border border-white/10 rounded-2xl overflow-hidden shadow-2xl flex font-sans h-[500px] md:h-[600px] text-left">
      
      {/* Sidebar - hidden on very small screens, visible on md */}
      <div className="w-64 bg-[#2B2D31] hidden md:flex flex-col border-r border-[#1E1F22]">
        {/* Server Header */}
        <div className="h-12 border-b border-[#1E1F22] flex items-center px-4 shadow-sm hover:bg-[#35373C] cursor-pointer transition-colors">
          <span className="font-bold text-white text-sm">Community Server</span>
        </div>
        
        {/* Channels List */}
        <div className="p-3 flex-1 overflow-y-auto">
          <div className="text-[10px] font-bold text-[#80848E] uppercase px-2 mb-1 mt-2">Text Channels</div>
          <div className="space-y-0.5">
            {CHANNELS.map((channel) => {
              const isActive = activeChannel === channel.id;
              return (
                <button
                  key={channel.id}
                  onClick={() => setActiveChannel(channel.id)}
                  className={cn(
                    "w-full flex items-center gap-2 px-2 py-1.5 rounded text-sm text-left transition-colors",
                    isActive
                      ? "bg-[#404249] text-white"
                      : "text-[#80848E] hover:bg-[#35373C] hover:text-[#DBDEE1]"
                  )}
                >
                  <span className="text-[#80848E] text-lg leading-none">#</span>
                  <span className="font-medium">{channel.name}</span>
                </button>
              );
            })}
          </div>
        </div>
        
        {/* User Profile Area */}
        <div className="h-14 bg-[#232428] flex items-center px-2 gap-2">
           <div className="w-8 h-8 rounded-full bg-indigo-500 flex items-center justify-center text-white font-bold text-xs shrink-0">Y</div>
           <div className="flex-1">
             <div className="text-white text-sm font-bold text-xs">You</div>
             <div className="text-[#80848E] text-[10px]">Online</div>
           </div>
        </div>
      </div>

      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col bg-[#313338] relative">
        
        {/* Mobile Channel Switcher (only visible on small screens) */}
        <div className="md:hidden h-12 border-b border-[#2B2D31] flex items-center px-4 shadow-sm gap-2 overflow-x-auto scrollbar-hide">
          {CHANNELS.map((channel) => (
            <button
              key={channel.id}
              onClick={() => setActiveChannel(channel.id)}
              className={cn(
                "px-3 py-1 rounded text-sm font-medium whitespace-nowrap transition-colors",
                activeChannel === channel.id ? "bg-[#404249] text-white" : "text-[#80848E] bg-[#2B2D31]"
              )}
            >
              # {channel.name}
            </button>
          ))}
        </div>

        {/* Channel Header (Desktop) */}
        <div className="hidden md:flex h-12 border-b border-[#2B2D31] items-center px-4 shadow-sm gap-2">
          <span className="text-[#80848E] text-xl">#</span>
          <span className="font-bold text-white text-sm">{CHANNELS.find(c => c.id === activeChannel)?.name}</span>
        </div>

        {/* Chat Content */}
        <div className="flex-1 p-4 overflow-y-auto flex flex-col justify-end gap-4">
          <AnimatePresence mode="wait">
            {activeChannel === "music" && <MusicVisual key="music" />}
            {activeChannel === "ai" && <AIVisual key="ai" />}
            {activeChannel === "mod" && <ModVisual key="mod" />}
            {activeChannel === "news" && <NewsVisual key="news" />}
            {activeChannel === "deals" && <DealsVisual key="deals" />}
            {activeChannel === "games" && <GamesVisual key="games" />}
          </AnimatePresence>
        </div>

        {/* Chat Input */}
        <div className="p-4 pt-0">
          <div className="bg-[#383A40] rounded-lg p-3 flex items-center gap-3">
             <div className="w-6 h-6 rounded-full bg-[#4E5058] flex items-center justify-center text-[#B5BAC1] font-bold text-lg leading-none shrink-0">+</div>
             <div className="text-[#80848E] text-sm">Message #{CHANNELS.find(c => c.id === activeChannel)?.name}</div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ----------------- DISCORD MESSAGE COMPONENTS ----------------- //

function MusicVisual() {
  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, transition: { duration: 0.1 } }} transition={{ duration: 0.2 }} className="flex flex-col gap-4">
      <div className="flex gap-4 hover:bg-[#2E3035] p-1 -mx-1 rounded transition-colors">
        <div className="w-10 h-10 rounded-full bg-emerald-500 shrink-0 flex items-center justify-center text-white font-bold">L</div>
        <div>
          <div className="text-white text-sm font-medium flex items-center gap-2">
            Luna <span className="text-xs text-[#80848E] font-normal">Today at 2:14 PM</span>
          </div>
          <div className="text-[#DBDEE1] text-sm flex items-center gap-1.5 mt-0.5">
            <span className="bg-[#383A40] text-[#00A8FC] px-1.5 py-0.5 rounded text-xs hover:bg-[#404249] cursor-pointer transition-colors">/play</span>
            lofi hip hop radio
          </div>
        </div>
      </div>

      <div className="flex gap-4 hover:bg-[#2E3035] p-1 -mx-1 rounded transition-colors">
        <img src="/logo.svg" className="w-10 h-10 rounded-full bg-[#111214] p-1 shrink-0 mt-0.5" alt="Tiffany" />
        <div className="flex-1">
          <div className="text-white font-medium text-sm flex items-center gap-2 mb-1">
            Tiffany Bot <span className="bg-[#5865F2] text-[10px] font-bold px-1.5 py-0.5 rounded text-white flex items-center gap-1"><CheckCircle className="w-3 h-3" /> APP</span>
            <span className="text-xs text-[#80848E] font-normal">Today at 2:14 PM</span>
          </div>
          
          <div className="bg-[#2B2D31] rounded flex flex-col border-l-4 border-[#ff479c] p-3 max-w-md">
            <div className="text-white font-bold flex items-center gap-2 mb-1 text-sm">
              <span className="text-[#ff479c]">♫</span> Now Playing
            </div>
            <div className="text-[#00A8FC] font-medium text-sm hover:underline cursor-pointer">Lofi Hip Hop Radio</div>
            <div className="text-[#DBDEE1] text-xs mb-3">Lofi Girl • 24/7 Radio</div>
            <div className="flex items-center gap-2 text-[#80848E] text-xs font-mono mb-3">
              <PlayCircle className="w-4 h-4 text-[#DBDEE1]" /> 00:42 ━━━━━━━━━━━━━━ 42:18
            </div>
            <div className="flex gap-2">
              <button className="bg-[#4E5058] hover:bg-[#6D6F78] text-white text-xs px-3 py-1.5 rounded transition-colors">Pause</button>
              <button className="bg-[#4E5058] hover:bg-[#6D6F78] text-white text-xs px-3 py-1.5 rounded transition-colors">Loop</button>
              <button className="bg-[#4E5058] hover:bg-[#6D6F78] text-white text-xs px-3 py-1.5 rounded transition-colors">Skip</button>
            </div>
          </div>
        </div>
      </div>
    </motion.div>
  );
}

function AIVisual() {
  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, transition: { duration: 0.1 } }} transition={{ duration: 0.2 }} className="flex flex-col gap-4">
      <div className="flex gap-4 hover:bg-[#2E3035] p-1 -mx-1 rounded transition-colors">
        <div className="w-10 h-10 rounded-full bg-indigo-500 shrink-0 flex items-center justify-center text-white font-bold">K</div>
        <div>
          <div className="text-white text-sm font-medium flex items-center gap-2">
            Kai <span className="text-xs text-[#80848E] font-normal">Today at 4:30 PM</span>
          </div>
          <div className="text-[#DBDEE1] text-sm flex items-center gap-1.5 mt-0.5">
            <span className="bg-[#383A40] text-[#00A8FC] px-1.5 py-0.5 rounded text-xs hover:bg-[#404249] cursor-pointer transition-colors">/chat</span>
            What is the optimal build for a Paladin in BG3?
          </div>
        </div>
      </div>

      <div className="flex gap-4 hover:bg-[#2E3035] p-1 -mx-1 rounded transition-colors">
        <img src="/logo.svg" className="w-10 h-10 rounded-full bg-[#111214] p-1 shrink-0 mt-0.5" alt="Tiffany" />
        <div className="flex-1">
          <div className="text-white font-medium text-sm flex items-center gap-2 mb-1">
            Tiffany Bot <span className="bg-[#5865F2] text-[10px] font-bold px-1.5 py-0.5 rounded text-white flex items-center gap-1"><CheckCircle className="w-3 h-3" /> APP</span>
            <span className="text-xs text-[#80848E] font-normal">Today at 4:30 PM</span>
          </div>
          
          <div className="text-[#DBDEE1] text-sm leading-relaxed max-w-2xl">
            For an optimal Paladin build in Baldur's Gate 3, focus on Strength and Charisma. The <strong>Oath of Vengeance</strong> subclass provides excellent single-target burst damage.<br/><br/>Pair it with the <em>Great Weapon Master</em> feat for massive critical hits, and ensure you keep Divine Smite ready for tough encounters.
          </div>
        </div>
      </div>
    </motion.div>
  );
}

function ModVisual() {
  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, transition: { duration: 0.1 } }} transition={{ duration: 0.2 }} className="flex flex-col gap-4">
      <div className="flex gap-4 hover:bg-[#2E3035] p-1 -mx-1 rounded transition-colors">
        <img src="/logo.svg" className="w-10 h-10 rounded-full bg-[#111214] p-1 shrink-0 mt-0.5" alt="Tiffany" />
        <div className="flex-1">
          <div className="text-white font-medium text-sm flex items-center gap-2 mb-1">
            Tiffany Bot <span className="bg-[#5865F2] text-[10px] font-bold px-1.5 py-0.5 rounded text-white flex items-center gap-1"><CheckCircle className="w-3 h-3" /> APP</span>
            <span className="text-xs text-[#80848E] font-normal">Today at 9:15 AM</span>
          </div>
          
          <div className="bg-[#2B2D31] rounded flex flex-col border-l-4 border-red-500 p-3 max-w-md">
            <div className="text-white font-bold flex items-center gap-2 mb-1 text-sm">
              <ShieldAlert className="w-4 h-4 text-red-500" /> Scam Link Detected
            </div>
            <div className="text-[#80848E] text-xs mb-2">Message from <strong>@suspicious_user</strong> deleted in #general</div>
            <div className="bg-[#1E1F22] rounded p-2 text-[#80848E] text-xs font-mono line-through mb-3">
              Hey everyone, claim your free nitro here: http://fake-discord-nitro.xyz
            </div>
            <div className="text-[#DBDEE1] text-xs font-medium flex items-center gap-2">
              <CheckCircle className="w-3 h-3 text-emerald-400" /> User timed out for 24 hours.
            </div>
          </div>
        </div>
      </div>
    </motion.div>
  );
}

function NewsVisual() {
  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, transition: { duration: 0.1 } }} transition={{ duration: 0.2 }} className="flex flex-col gap-4">
      <div className="flex gap-4 hover:bg-[#2E3035] p-1 -mx-1 rounded transition-colors">
        <img src="/logo.svg" className="w-10 h-10 rounded-full bg-[#111214] p-1 shrink-0 mt-0.5" alt="Tiffany" />
        <div className="flex-1">
          <div className="text-white font-medium text-sm flex items-center gap-2 mb-1">
            Tiffany Bot <span className="bg-[#5865F2] text-[10px] font-bold px-1.5 py-0.5 rounded text-white flex items-center gap-1"><CheckCircle className="w-3 h-3" /> APP</span>
            <span className="text-xs text-[#80848E] font-normal">Today at 10:02 AM</span>
          </div>
          
          <div className="bg-[#2B2D31] rounded flex flex-col border-l-4 border-[var(--color-tiffany-primary)] p-3 max-w-md">
            <div className="text-[#00A8FC] font-bold mb-2 text-sm hover:underline cursor-pointer">Apple just announced their latest lineup of processors</div>
            <div className="text-[#DBDEE1] text-xs mb-3 line-clamp-3">
              The new architecture brings a staggering 40% performance increase for developers, alongside massive battery life improvements across the board...
            </div>
            <div className="text-[10px] text-[#80848E] font-medium flex items-center gap-2">
              <span className="bg-[#1E1F22] px-1.5 py-0.5 rounded">The Verge</span>
              <span>•</span>
              <span>Published 5m ago</span>
            </div>
          </div>
        </div>
      </div>
    </motion.div>
  );
}

function DealsVisual() {
  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, transition: { duration: 0.1 } }} transition={{ duration: 0.2 }} className="flex flex-col gap-4">
      <div className="flex gap-4 hover:bg-[#2E3035] p-1 -mx-1 rounded transition-colors">
        <img src="/logo.svg" className="w-10 h-10 rounded-full bg-[#111214] p-1 shrink-0 mt-0.5" alt="Tiffany" />
        <div className="flex-1">
          <div className="text-white font-medium text-sm flex items-center gap-2 mb-1">
            Tiffany Bot <span className="bg-[#5865F2] text-[10px] font-bold px-1.5 py-0.5 rounded text-white flex items-center gap-1"><CheckCircle className="w-3 h-3" /> APP</span>
            <span className="text-xs text-[#80848E] font-normal">Today at 1:45 PM</span>
          </div>
          
          <div className="bg-[#2B2D31] rounded flex flex-col border-l-4 border-amber-500 p-3 max-w-md">
            <div className="text-[#00A8FC] font-bold mb-2 text-sm hover:underline cursor-pointer">🔥 SSD NVMe 1TB Gen 4 - High Speed</div>
            <div className="flex items-center gap-2 mb-4">
              <span className="text-emerald-400 font-bold">R$ 299,90</span>
              <span className="text-[#80848E] line-through text-xs">R$ 379,90</span>
              <span className="bg-red-500/20 text-red-400 px-1.5 py-0.5 rounded text-[10px] font-bold">-21%</span>
            </div>
            <button className="w-full bg-[#4E5058] hover:bg-[#6D6F78] text-white text-xs font-medium py-2 rounded transition-colors flex items-center justify-center gap-2">
              Comprar na Amazon
            </button>
          </div>
        </div>
      </div>
    </motion.div>
  );
}

function GamesVisual() {
  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, transition: { duration: 0.1 } }} transition={{ duration: 0.2 }} className="flex flex-col gap-4">
      <div className="flex gap-4 hover:bg-[#2E3035] p-1 -mx-1 rounded transition-colors">
        <div className="w-10 h-10 rounded-full bg-rose-500 shrink-0 flex items-center justify-center text-white font-bold">N</div>
        <div>
          <div className="text-white text-sm font-medium flex items-center gap-2">
            Nova <span className="text-xs text-[#80848E] font-normal">Today at 7:22 PM</span>
          </div>
          <div className="text-[#DBDEE1] text-sm flex items-center gap-1.5 mt-0.5">
             <span className="bg-[#383A40] text-[#00A8FC] px-1.5 py-0.5 rounded text-xs hover:bg-[#404249] cursor-pointer transition-colors">/roll</span>
             4d6
          </div>
        </div>
      </div>

      <div className="flex gap-4 hover:bg-[#2E3035] p-1 -mx-1 rounded transition-colors">
        <img src="/logo.svg" className="w-10 h-10 rounded-full bg-[#111214] p-1 shrink-0 mt-0.5" alt="Tiffany" />
        <div className="flex-1">
          <div className="text-white font-medium text-sm flex items-center gap-2 mb-1">
            Tiffany Bot <span className="bg-[#5865F2] text-[10px] font-bold px-1.5 py-0.5 rounded text-white flex items-center gap-1"><CheckCircle className="w-3 h-3" /> APP</span>
            <span className="text-xs text-[#80848E] font-normal">Today at 7:22 PM</span>
          </div>
          
          <div className="text-[#DBDEE1] text-sm font-mono bg-[#2B2D31] px-3 py-2 rounded border border-[#1E1F22] inline-block">
            🎲 6 + 4 + 5 + 3 = <strong className="text-white text-lg ml-1">18</strong>
          </div>
        </div>
      </div>
    </motion.div>
  );
}
