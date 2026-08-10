"use client";

import Link from "next/link";
import { ArrowRight, Bot, Command, Settings } from "lucide-react";
import { cn } from "@/lib/utils";
import { motion, AnimatePresence } from "framer-motion";
import { useState, useEffect } from "react";

import { ProductExplorer } from "@/components/home/ProductExplorer";
import { FeatureNews, FeatureDeals } from "@/components/home/FeatureNewsDeals";
import { FeatureMusic } from "@/components/home/FeatureMusic";
import { PremiumComparison } from "@/components/home/PremiumComparison";
import { Footer } from "@/components/layout/Footer";
import { PinkParticles } from "@/components/home/PinkParticles";
import { HeroDiscordSimulation } from "@/components/home/HeroDiscordSimulation";

export default function Home() {
  return (
    <div className="min-h-screen bg-[#050507] overflow-hidden selection:bg-[var(--color-tiffany-primary)]/30 text-white font-sans">
      
      {/* Background System */}
      <div className="fixed inset-0 z-0 pointer-events-none overflow-hidden">
        <PinkParticles />
        <div className="absolute top-[-20%] left-[-10%] w-[70vw] h-[70vw] rounded-full bg-[var(--color-tiffany-primary)]/10 blur-[140px] mix-blend-screen" />
        <div className="absolute top-[10%] right-[-20%] w-[60vw] h-[60vw] rounded-full bg-[#ff479c]/5 blur-[140px] mix-blend-screen" />
        <div className="absolute inset-0 opacity-[0.02] bg-[url('https://grainy-gradients.vercel.app/noise.svg')]" />
      </div>

      {/* Navbar */}
      <nav className="fixed top-0 w-full z-50 bg-[#050507]/80 backdrop-blur-xl border-b border-white/5">
        <div className="max-w-[1400px] mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3 group cursor-pointer">
            <div className="w-8 h-8 flex items-center justify-center group-hover:scale-105 transition-transform">
              <img src="/logo.svg" className="w-8 h-8 object-contain" alt="Tiffany Logo" />
            </div>
            <span className="text-xl font-bold tracking-tight">Tiffany</span>
          </div>
          
          <div className="hidden md:flex items-center gap-8 text-sm font-medium text-zinc-400">
            <Link href="#features" className="hover:text-white transition-colors">Features</Link>
            <Link href="#news-deals" className="hover:text-white transition-colors">News & Deals</Link>
            <Link href="/commands" className="hover:text-white transition-colors">Commands</Link>
            <Link href="#premium" className="hover:text-white transition-colors">Premium</Link>
          </div>
          
          <div className="flex items-center gap-4">
            <Link href="/api/auth/login" className="text-sm font-medium hover:text-white text-zinc-400 transition-colors hidden sm:block">
              Sign In
            </Link>
            <Link href="/dashboard" className="h-9 px-4 flex items-center justify-center text-sm font-semibold bg-white text-black rounded-full hover:bg-gray-200 transition-colors shadow-[0_0_20px_rgba(255,255,255,0.1)]">
              Dashboard
            </Link>
          </div>
        </div>
      </nav>

      <main className="relative z-10 w-full pt-32 pb-0 px-6 flex flex-col items-center">
        
        {/* HERO */}
        <section className="max-w-[1400px] w-full min-h-[85vh] flex flex-col justify-center mb-32 relative">
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-12 items-center">
            <div className="lg:col-span-5 flex flex-col items-start z-10">
              <motion.div 
                initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3 }}
                className="mb-6 px-3 py-1 rounded-full border border-white/10 bg-white/5 backdrop-blur-md flex items-center gap-2 text-xs font-semibold tracking-wider text-zinc-400 uppercase"
              >
                <div className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" /> Tiffany Bot 2.5
              </motion.div>
              
              <motion.h1 
                initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4, delay: 0.05 }}
                className="text-5xl sm:text-6xl md:text-[5rem] font-medium tracking-tight leading-[1.05] mb-8"
              >
                One bot.<br />
                <span className="text-zinc-500">Your entire server.</span>
              </motion.h1>
              
              <motion.p 
                initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4, delay: 0.1 }}
                className="text-xl text-zinc-400 mb-10 max-w-md leading-relaxed font-light"
              >
                Music, AI, moderation, news, deals and games — all inside Discord.
              </motion.p>
              
              <motion.div 
                initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4, delay: 0.15 }}
                className="flex flex-col sm:flex-row gap-4 w-full sm:w-auto"
              >
                <Link href="/api/auth/login">
                  <motion.div 
                    whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }}
                    className="group h-12 px-6 cursor-pointer flex items-center justify-center gap-2 text-sm font-semibold bg-white text-black rounded-full transition-shadow hover:shadow-[0_0_20px_rgba(255,255,255,0.2)]"
                  >
                    Add to Discord <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
                  </motion.div>
                </Link>
                <Link href="/commands">
                  <motion.div 
                    whileHover={{ scale: 1.05, backgroundColor: "rgba(255,255,255,0.1)" }} whileTap={{ scale: 0.95 }}
                    className="h-12 px-6 cursor-pointer flex items-center justify-center gap-2 text-sm font-semibold bg-white/5 border border-white/10 rounded-full transition-colors"
                  >
                    <Command className="w-4 h-4" /> Explore Commands
                  </motion.div>
                </Link>
              </motion.div>
            </div>

            {/* Abstract Hero Server Visualization */}
            <div className="lg:col-span-7 relative h-[600px] w-full hidden lg:block perspective-1000">
              <HeroDiscordSimulation />
            </div>
          </div>
        </section>

        {/* PRODUCT EXPLORER */}
        <motion.section 
          initial={{ opacity: 0, y: 30 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-100px" }}
          transition={{ duration: 0.6, ease: "easeOut" }}
          id="features" 
          className="w-full mb-40 flex flex-col items-center"
        >
          <div className="text-center mb-16">
            <h2 className="text-4xl md:text-5xl font-medium tracking-tight mb-4">Everything your server needs.<br/>One bot.</h2>
          </div>
          <ProductExplorer />
        </motion.section>

        {/* NEWS, DEALS, MUSIC NARRATIVE */}
        <section id="news-deals" className="w-full flex flex-col items-center">
          <FeatureNews />
          <FeatureDeals />
          <FeatureMusic />
        </section>

        {/* COMMAND SANDBOX CTA */}
        <motion.section 
          initial={{ opacity: 0, y: 30 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-100px" }}
          transition={{ duration: 0.6, ease: "easeOut" }}
          className="w-full text-center mb-40 flex flex-col items-center"
        >
          <div className="w-16 h-16 rounded-2xl bg-white/5 border border-white/10 flex items-center justify-center mb-6">
            <Command className="w-8 h-8 text-fuchsia-400" />
          </div>
          <h2 className="text-4xl md:text-5xl font-medium tracking-tight mb-6">
            See every command.
          </h2>
          <p className="text-xl text-zinc-400 font-light mb-10 max-w-2xl mx-auto">
            Explore what Tiffany can do before you invite her.
          </p>
          <Link href="/commands">
            <motion.div 
              whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }}
              className="inline-flex cursor-pointer items-center justify-center gap-2 h-14 px-8 text-lg font-semibold bg-white/10 text-white border border-white/20 rounded-full transition-colors hover:bg-white/20"
            >
              Explore all commands <ArrowRight className="w-4 h-4" />
            </motion.div>
          </Link>
        </motion.section>

        {/* DASHBOARD NARRATIVE */}
        <motion.section 
          initial={{ opacity: 0, scale: 0.95 }}
          whileInView={{ opacity: 1, scale: 1 }}
          viewport={{ once: true, margin: "-100px" }}
          transition={{ duration: 0.7, ease: "easeOut" }}
          className="w-full max-w-[1200px] mb-40 text-center bg-white/[0.02] backdrop-blur-2xl border border-white/10 rounded-3xl p-16 relative overflow-hidden shadow-[0_8px_32px_0_rgba(0,0,0,0.36)]"
        >
          <div className="absolute top-0 right-0 w-[500px] h-[500px] bg-[var(--color-tiffany-primary)]/10 blur-[120px] pointer-events-none rounded-full" />
          <div className="relative z-10">
            <motion.div 
              initial={{ scale: 0 }} whileInView={{ scale: 1 }} viewport={{ once: true }} transition={{ type: "spring", delay: 0.2 }}
              className="w-20 h-20 mx-auto bg-white/5 border border-white/10 rounded-2xl flex items-center justify-center mb-8 drop-shadow-[0_0_20px_rgba(192,38,211,0.2)]"
            >
              <Settings className="w-10 h-10 text-[var(--color-tiffany-primary)]" />
            </motion.div>
            <h2 className="text-4xl md:text-5xl font-medium tracking-tight mb-6">Your server.<br/>Your settings.</h2>
            <p className="text-xl text-zinc-400 font-light mb-10 max-w-2xl mx-auto">
              Connect Discord and configure Tiffany from one place.
              <br /><br />
              <span className="text-sm font-medium text-zinc-500 uppercase tracking-widest">
                Moderation • News • Deals • Music • AI
              </span>
            </p>
            <Link href="/dashboard">
              <motion.div 
                whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }}
                className="inline-flex cursor-pointer items-center justify-center gap-2 h-14 px-8 text-lg font-semibold bg-white text-black rounded-full shadow-[0_0_30px_rgba(255,255,255,0.15)] transition-shadow hover:shadow-[0_0_40px_rgba(255,255,255,0.3)]"
              >
                Open Control Center
              </motion.div>
            </Link>
          </div>
        </motion.section>

        {/* PREMIUM NARRATIVE */}
        <div id="premium" className="w-full">
          <PremiumComparison />
        </div>

        {/* FINAL CTA */}
        <motion.section 
          initial={{ opacity: 0, y: 30 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-100px" }}
          transition={{ duration: 0.6, ease: "easeOut" }}
          className="w-full text-center py-32"
        >
          <h2 className="text-4xl md:text-5xl font-medium tracking-tight mb-10">Ready to bring Tiffany in?</h2>
          
          <div className="flex flex-col sm:flex-row justify-center gap-4 w-full sm:w-auto">
            <Link href="/api/auth/login">
              <motion.div 
                whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }}
                className="group h-14 px-8 cursor-pointer flex items-center justify-center gap-2 text-lg font-semibold bg-[var(--color-tiffany-primary)] text-white rounded-full transition-shadow hover:shadow-[0_0_30px_rgba(192,38,211,0.3)]"
              >
                Add Tiffany to Discord <ArrowRight className="w-5 h-5 group-hover:translate-x-1 transition-transform" />
              </motion.div>
            </Link>
            <Link href="/commands">
              <motion.div 
                whileHover={{ scale: 1.05, backgroundColor: "rgba(255,255,255,0.1)" }} whileTap={{ scale: 0.95 }}
                className="h-14 px-8 cursor-pointer flex items-center justify-center gap-2 text-lg font-semibold bg-white/5 border border-white/10 rounded-full transition-colors"
              >
                <Command className="w-5 h-5" /> Explore Commands
              </motion.div>
            </Link>
          </div>
        </motion.section>

      </main>

      <Footer />
    </div>
  );
}


