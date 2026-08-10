"use client";

import { Check, X, Crown, Star, Server } from "lucide-react";
import { cn } from "@/lib/utils";
import { motion } from "framer-motion";

const TIERS = [
  {
    name: "Free",
    icon: Star,
    color: "text-zinc-400",
    bg: "bg-zinc-400/10",
    border: "border-white/10",
    description: "For getting started.",
    price: "$0",
    features: [
      { name: "Basic Moderation", included: true },
      { name: "Standard Audio", included: true },
      { name: "3 News Sources", included: true },
      { name: "Basic Games", included: true },
    ]
  },
  {
    name: "Tiffany Plus",
    icon: Crown,
    color: "text-[var(--color-tiffany-primary)]",
    bg: "bg-[var(--color-tiffany-primary)]/10",
    border: "border-[var(--color-tiffany-primary)]",
    description: "For individual power users.",
    price: "$4.99",
    period: "/mo",
    popular: true,
    features: [
      { name: "High-Bitrate Audio", included: true },
      { name: "10 News Sources", included: true },
      { name: "24/7 Playback", included: true },
      { name: "Priority AI", included: true },
    ]
  },
  {
    name: "Server Premium",
    icon: Server,
    color: "text-amber-400",
    bg: "bg-amber-400/10",
    border: "border-amber-400/30",
    description: "For communities and creators.",
    price: "$14.99",
    period: "/mo",
    features: [
      { name: "Advanced Automations", included: true },
      { name: "Unlimited News", included: true },
      { name: "Custom Branding", included: true },
      { name: "Priority AI", included: true },
    ]
  }
];

export function PremiumComparison() {
  return (
    <section className="w-full max-w-[1200px] mx-auto mb-40 px-6">
      <div className="text-center mb-16">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-amber-500/10 border border-amber-500/20 text-amber-500 text-sm font-medium mb-6 uppercase tracking-wider">
          <Crown className="w-4 h-4" />
          <span>Tiffany Premium</span>
        </div>
        <h2 className="text-4xl md:text-5xl font-medium tracking-tight mb-4">More power when you need it.</h2>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-8 relative">
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[80%] h-[50%] bg-[var(--color-tiffany-primary)]/10 blur-[120px] pointer-events-none -z-10 rounded-full" />
        
        {TIERS.map((tier, index) => (
          <motion.div 
            key={tier.name}
            initial={{ opacity: 0, y: 30 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: "-50px" }}
            transition={{ duration: 0.5, delay: index * 0.15, ease: "easeOut" }}
            className="flex flex-col"
          >
            <div
              className={cn(
                "bg-white/[0.02] backdrop-blur-xl rounded-3xl p-8 border flex flex-col flex-1 relative transition-all duration-300 hover:-translate-y-2",
                tier.popular ? "border-[var(--color-tiffany-primary)] shadow-[0_0_30px_rgba(192,38,211,0.15)] hover:shadow-[0_0_50px_rgba(192,38,211,0.25)]" : "border-white/10 hover:border-white/20",
              )}
            >
              {tier.popular && (
                <div className="absolute -top-4 left-1/2 -translate-x-1/2 bg-[var(--color-tiffany-primary)] text-white text-xs font-bold uppercase tracking-wider px-3 py-1 rounded-full">
                  Most Popular
                </div>
              )}
              
              <div className="flex items-center gap-3 mb-4">
                <div className={cn("w-10 h-10 rounded-xl flex items-center justify-center", tier.bg, tier.color)}>
                  <tier.icon className="w-5 h-5" />
                </div>
                <h3 className="text-xl font-bold text-white">{tier.name}</h3>
              </div>
              
              <p className="text-sm text-zinc-400 mb-6">{tier.description}</p>
              
              <div className="mb-8">
                <span className="text-4xl font-bold text-white">{tier.price}</span>
                {tier.period && <span className="text-zinc-500">{tier.period}</span>}
              </div>
              
              <div className="space-y-4 mb-8 flex-1">
                {tier.features.map((feature, i) => (
                  <div key={i} className="flex items-center gap-3">
                    {feature.included ? (
                      <Check className={cn("w-4 h-4", tier.color)} />
                    ) : (
                      <X className="w-4 h-4 text-zinc-600" />
                    )}
                    <span className={cn("text-sm font-medium", feature.included ? "text-zinc-200" : "text-zinc-600")}>
                      {feature.name}
                    </span>
                  </div>
                ))}
              </div>
              
              <motion.button 
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
                className={cn(
                  "w-full py-3 rounded-xl font-bold transition-colors",
                  tier.popular 
                    ? "bg-[var(--color-tiffany-primary)] text-white hover:bg-[#a21caf]" 
                    : "bg-white/5 text-white hover:bg-white/10"
                )}
              >
                {tier.price === "$0" ? "Add to Discord" : "Upgrade Now"}
              </motion.button>
            </div>
          </motion.div>
        ))}
      </div>
    </section>
  );
}
