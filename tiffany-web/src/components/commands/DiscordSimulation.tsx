"use client";

import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Command, CommandPreview, DiscordResponse, DiscordEmbedField, DiscordButton as DiscordButtonType } from "@/data/commands";
import { CheckCircle, PlayCircle, Hash } from "lucide-react";

export function DiscordSimulation({ command }: { command: Command }) {
  // Restart sequence when command changes
  const [activeStep, setActiveStep] = useState(0);

  useEffect(() => {
    setActiveStep(0); // reset to initial state
    
    if (!command.preview || !command.preview.responses) return;
    
    let currentStep = 0;
    const timeouts: NodeJS.Timeout[] = [];
    
    // Schedule each response based on its delay
    for (let i = 0; i < command.preview.responses.length; i++) {
      const response = command.preview.responses[i];
      const delay = response.delayMs || 300;
      
      const timeout = setTimeout(() => {
        currentStep++;
        setActiveStep(currentStep);
      }, delay * (i + 1)); // Accumulative delay for simplicity in sequence
      
      timeouts.push(timeout);
    }
    
    return () => {
      timeouts.forEach(clearTimeout);
    };
  }, [command.name]);

  if (!command.preview) {
    return (
      <div className="bg-[#313338] rounded-xl p-8 text-center text-zinc-400">
        Preview not available for this command.
      </div>
    );
  }

  const { preview } = command;
  const visibleResponses = preview.responses.slice(0, activeStep);

  return (
    <div className="bg-[#313338] rounded-xl text-left shadow-2xl border border-white/5 overflow-hidden font-sans flex flex-col">
      {/* Discord Header */}
      <div className="h-12 border-b border-[#1E1F22] flex items-center px-4 shrink-0 shadow-sm gap-2">
        <Hash className="w-5 h-5 text-[#80848E]" />
        <span className="font-bold text-white text-[15px]">{preview.channel.name}</span>
      </div>

      {/* Messages Area */}
      <div className="p-4 flex flex-col gap-4">
        <AnimatePresence mode="popLayout">
          {/* USER COMMAND INPUT */}
          <motion.div
            key="user_input"
            initial={{ opacity: 0, y: 5 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.15 }}
          >
            <DiscordMessage 
              username={preview.actor.username} 
              avatar={preview.actor.avatar} 
              avatarColor={preview.actor.color}
            >
              <div className="flex items-center gap-1.5 mt-0.5">
                <span className="text-[#DBDEE1] text-[15px]">
                  <span className="bg-[#404249]/50 text-[#DBDEE1] px-1 rounded font-mono text-sm mr-1">
                    {preview.interaction.input.split(" ")[0]}
                  </span>
                  {preview.interaction.input.split(" ").slice(1).join(" ")}
                </span>
              </div>
            </DiscordMessage>
          </motion.div>

          {/* BOT RESPONSES */}
          {visibleResponses.map((res) => (
            <motion.div
              key={res.id}
              initial={{ opacity: 0, y: 5 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.2 }}
            >
              <DiscordMessage 
                username="Tiffany Bot" 
                avatar="/logo.svg" 
                isBot
                ephemeral={res.ephemeral}
              >
                {res.type === "thinking" && (
                  <span className="text-[#DBDEE1] italic">Tiffany is thinking...</span>
                )}
                
                {res.content && (
                  <div className="text-[#DBDEE1] mb-2 text-[15px]">{res.content}</div>
                )}
                
                {res.embed && (
                  <DiscordEmbed embed={res.embed} />
                )}
                
                {res.components && res.components.map((row, idx) => (
                  <div key={idx} className="flex flex-wrap gap-2 mt-2">
                    {row.buttons.map((btn, bIdx) => (
                      <DiscordButton key={bIdx} button={btn} />
                    ))}
                  </div>
                ))}
              </DiscordMessage>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </div>
  );
}

// ---------------------------------------------------------
// DISCORD PRIMITIVE COMPONENTS
// ---------------------------------------------------------

function DiscordMessage({ 
  username, 
  avatar, 
  avatarColor, 
  isBot, 
  ephemeral, 
  children 
}: { 
  username: string, 
  avatar: string, 
  avatarColor?: string, 
  isBot?: boolean,
  ephemeral?: boolean,
  children: React.ReactNode 
}) {
  return (
    <div className={`flex items-start gap-4 ${ephemeral ? 'bg-[#5865F2]/10 p-2 -mx-2 rounded' : ''}`}>
      <div className={`w-10 h-10 rounded-full shrink-0 flex items-center justify-center overflow-hidden ${avatarColor || 'bg-[#2B2D31]'}`}>
        {avatar.startsWith('/') ? (
          <img src={avatar} className={`w-full h-full object-contain ${isBot ? 'bg-[#111214] p-1' : ''}`} alt={username} />
        ) : (
          <span className="text-white font-bold">{avatar}</span>
        )}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-0.5">
          <span className="text-white font-medium hover:underline cursor-pointer">{username}</span>
          {isBot && (
            <span className="bg-[#5865F2] text-[10px] font-bold px-1.5 py-0.5 rounded text-white flex items-center gap-1">
              <CheckCircle className="w-3 h-3" /> APP
            </span>
          )}
          <span className="text-[#80848E] text-xs font-medium ml-1">Today at 12:00 PM</span>
        </div>
        <div>
          {children}
        </div>
        {ephemeral && (
          <div className="text-[#80848E] text-xs mt-1 flex items-center gap-1">
            <span className="font-bold text-[#5865F2]">Only you can see this</span> • <span className="hover:underline cursor-pointer">Dismiss message</span>
          </div>
        )}
      </div>
    </div>
  );
}

function DiscordEmbed({ embed }: { embed: NonNullable<DiscordResponse["embed"]> }) {
  return (
    <div 
      className="bg-[#2B2D31] rounded max-w-[520px] p-4 flex flex-col gap-2 mt-1 border-l-4"
      style={{ borderLeftColor: embed.color || "#1E1F22" }}
    >
      {embed.title && (
        <div className="text-white font-bold text-[15px]">{embed.title}</div>
      )}
      {embed.description && (
        <div className="text-[#DBDEE1] text-[14px] whitespace-pre-wrap leading-[1.375] font-normal" dangerouslySetInnerHTML={{__html: parseMarkdown(embed.description)}}></div>
      )}
      {embed.fields && embed.fields.length > 0 && (
        <div className="flex flex-wrap gap-x-4 gap-y-2 mt-2">
          {embed.fields.map((f, i) => (
            <div key={i} className={`${f.inline ? 'min-w-[150px] flex-1' : 'w-full'}`}>
              <div className="text-white text-sm font-bold mb-0.5">{f.name}</div>
              <div className="text-[#DBDEE1] text-sm" dangerouslySetInnerHTML={{__html: parseMarkdown(f.value)}}></div>
            </div>
          ))}
        </div>
      )}
      {embed.footer && (
        <div className="text-[#DBDEE1] text-xs mt-2 flex items-center gap-2">
          {embed.footer}
        </div>
      )}
    </div>
  );
}

function DiscordButton({ button }: { button: DiscordButtonType }) {
  const styles = {
    primary: "bg-[#5865F2] hover:bg-[#4752C4] text-white",
    secondary: "bg-[#4E5058] hover:bg-[#6D6F78] text-white",
    success: "bg-[#248046] hover:bg-[#1A6334] text-white",
    danger: "bg-[#DA373C] hover:bg-[#A12828] text-white",
  };

  return (
    <button className={`px-4 py-1.5 rounded transition-colors text-sm font-medium flex items-center gap-2 h-8 ${styles[button.style]}`}>
      {button.emoji && <span>{button.emoji}</span>}
      {button.label}
    </button>
  );
}

// Simple markdown parser to handle bold and code blocks in descriptions
function parseMarkdown(text: string) {
  let html = text;
  html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/`(.*?)`/g, '<code class="bg-[#1E1F22] rounded px-1 text-[13px] font-mono">$1</code>');
  html = html.replace(/<@&?(\d+)>/g, '<span class="bg-[#5865F2]/20 text-[#C9CDFB] px-1 rounded font-medium hover:bg-[#5865F2] hover:text-white cursor-pointer cursor-pointer">@role/user</span>');
  html = html.replace(/<#(\d+)>/g, '<span class="bg-[#5865F2]/20 text-[#C9CDFB] px-1 rounded font-medium hover:bg-[#5865F2] hover:text-white cursor-pointer cursor-pointer">#channel</span>');
  html = html.replace(/\[(.*?)\]\((.*?)\)/g, '<a href="#" class="text-[#00A8FC] hover:underline">$1</a>');
  return html;
}
