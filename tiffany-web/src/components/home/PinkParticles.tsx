"use client";

import { useState, useEffect, useRef } from "react";
import { motion } from "framer-motion";

export function PinkParticles() {
  const [particles, setParticles] = useState<any[]>([]);
  
  const spotlightRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Generate 70 particles for a subtle environmental atmosphere
    const maxParticles = 70;
    const newParticles = Array.from({ length: maxParticles }).map((_, i) => {
      const isSymbol = Math.random() > 0.90; // 10% chance to be the Tiffany logo
      return {
        id: i,
        x: Math.random() * 100,
        y: Math.random() * 100,
        size: isSymbol ? Math.random() * 20 + 15 : Math.random() * 6 + 1,
        duration: Math.random() * 20 + 15, // Faster movement
        delay: Math.random() * 5,
        opacity: Math.random() * 0.4 + 0.1,
        isSymbol
      };
    });
    setParticles(newParticles);

    // Mouse movement listener - pure DOM for zero latency
    const handleMouseMove = (e: MouseEvent) => {
      if (spotlightRef.current) {
        // Use translate3d for hardware acceleration, combined with -50% to center perfectly on the exact pixel
        spotlightRef.current.style.transform = `translate3d(${e.clientX}px, ${e.clientY}px, 0) translate(-50%, -50%)`;
      }
    };
    
    // Set initial position to center
    if (typeof window !== "undefined") {
      if (spotlightRef.current) {
        spotlightRef.current.style.transform = `translate3d(${window.innerWidth / 2}px, ${window.innerHeight / 2}px, 0) translate(-50%, -50%)`;
      }
      window.addEventListener("mousemove", handleMouseMove, { passive: true });
    }
    
    return () => {
      if (typeof window !== "undefined") {
        window.removeEventListener("mousemove", handleMouseMove);
      }
    };
  }, []);

  return (
    <>
      {/* BACKGROUND PARTICLES - z-0 (behind cards) */}
      <div className="fixed inset-0 z-0 pointer-events-none overflow-hidden" aria-hidden="true">
        {particles.map((p) => (
          <motion.div
            key={p.id}
            className="absolute rounded-full"
            style={{
              left: `${p.x}%`,
              top: `${p.y}%`,
              width: p.size,
              height: p.size,
              backgroundColor: p.isSymbol ? "transparent" : "var(--color-tiffany-primary)",
              backgroundImage: p.isSymbol ? "url('/logo.svg')" : "none",
              backgroundSize: "contain",
              backgroundPosition: "center",
              backgroundRepeat: "no-repeat",
              opacity: p.opacity,
              filter: p.isSymbol ? "none" : "blur(1px)",
              boxShadow: p.isSymbol ? "none" : `0 0 ${p.size * 2}px var(--color-tiffany-primary)`,
            }}
            animate={{
              y: ["0vh", "-110vh"],
              x: ["0vw", `${Math.random() * 30 - 15}vw`],
              rotate: p.isSymbol ? [0, 720] : 0,
              scale: [1, 1.2, 1],
            }}
            transition={{
              y: { duration: p.duration, delay: p.delay, repeat: Infinity, ease: "linear" },
              x: { duration: p.duration, delay: p.delay, repeat: Infinity, ease: "easeInOut" },
              rotate: { duration: p.duration * 1.5, repeat: Infinity, ease: "linear" },
              scale: { duration: p.duration / 3, repeat: Infinity, ease: "easeInOut" },
            }}
          />
        ))}
      </div>

      {/* MOUSE SPOTLIGHT - z-[100] (over cards) */}
      <div className="fixed inset-0 z-[100] pointer-events-none overflow-hidden" aria-hidden="true">
        <div
          ref={spotlightRef}
          className="absolute top-0 left-0 w-[800px] h-[800px] rounded-full mix-blend-screen opacity-60 pointer-events-none will-change-transform"
          style={{
            background: "radial-gradient(circle, rgba(217, 70, 239, 0.15) 0%, rgba(217, 70, 239, 0.05) 20%, transparent 60%)"
          }}
        />
      </div>
    </>
  );
}
