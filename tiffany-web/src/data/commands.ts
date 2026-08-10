export type CommandCategory = "Music" | "AI & Fun" | "Embeds" | "Giveaways" | "Utility";

export type DiscordEmbedField = {
  name: string;
  value: string;
  inline?: boolean;
};

export type DiscordButton = {
  label: string;
  style: "primary" | "secondary" | "success" | "danger";
  emoji?: string;
};

export type DiscordResponse = {
  id: string; // for React keys
  type: "thinking" | "message" | "embed" | "modal";
  ephemeral?: boolean;
  content?: string;
  embed?: {
    color?: string;
    title?: string;
    description?: string;
    fields?: DiscordEmbedField[];
    footer?: string;
    thumbnail?: string;
  };
  components?: {
    type: "action_row";
    buttons: DiscordButton[];
  }[];
  delayMs?: number; // artificial delay before showing this specific response in sequence
};

export type CommandPreview = {
  syntax: string;
  actor: { username: string; avatar: string; color: string; };
  channel: { name: string; type: "text" | "voice" };
  interaction: {
    input: string;
    autocomplete?: string[];
  };
  responses: DiscordResponse[];
};

export interface Command {
  name: string;
  category: CommandCategory;
  description: string;
  usage: string;
  examples: string[];
  permissions?: string;
  premium?: boolean;
  related?: string[];
  subcommands?: Command[];
  preview?: CommandPreview;
}

const BRAND_PINK = "#FF2D78";
const GREEN = "#57F287";

export const COMMANDS: Command[] = [
  // ============================
  // MUSIC COMMANDS
  // ============================
  {
    name: "/play",
    category: "Music",
    description: "Plays a song by name or URL directly inside your voice channel.",
    usage: "/play query:<song or URL>",
    examples: ["/play lofi hip hop radio"],
    related: ["/queue", "/skip", "/pause"],
    preview: {
      syntax: "/play query: lofi hip hop radio",
      actor: { username: "Maya", avatar: "M", color: "bg-fuchsia-500" },
      channel: { name: "music", type: "text" },
      interaction: {
        input: "/play query: lofi hip hop radio",
        autocomplete: ["lofi hip hop radio - beats to relax/study to", "lofi girl", "chillhop"]
      },
      responses: [
        {
          id: "play_status",
          type: "embed",
          delayMs: 150,
          embed: {
            color: BRAND_PINK,
            description: "🔊 Conectada a **Lounge**\n🔎 Buscando **lofi hip hop radio**...",
          }
        },
        {
          id: "play_added",
          type: "embed",
          delayMs: 600,
          embed: {
            color: BRAND_PINK,
            description: "🎵 **Adicionado à fila: lofi hip hop radio - beats to relax/study to**\n\n⏱️ Duração: 0:00 (Live) · 🔢 Posição na fila: #1 · 👤 Pedido por: Maya",
          }
        }
      ]
    }
  },
  {
    name: "/queue",
    category: "Music",
    description: "Displays the current audio queue and the currently playing track.",
    usage: "/queue",
    examples: ["/queue"],
    related: ["/skip", "/play", "/clear"],
    preview: {
      syntax: "/queue",
      actor: { username: "Nico", avatar: "N", color: "bg-emerald-500" },
      channel: { name: "music", type: "text" },
      interaction: { input: "/queue" },
      responses: [
        {
          id: "queue_view",
          type: "embed",
          delayMs: 150,
          embed: {
            color: BRAND_PINK,
            title: "🎶 Fila de Reprodução",
            description: "**Tocando Agora:**\n[lofi hip hop radio](https://youtube.com) | `Live` | Pedido por Maya\n\n**Próximas:**\n1. [Chillstep Mix 2024](https://youtube.com) | `45:12` | Pedido por Nico\n2. [Synthwave Radio](https://youtube.com) | `Live` | Pedido por Kai",
            footer: "2 músicas na fila"
          }
        }
      ]
    }
  },
  {
    name: "/pause",
    category: "Music",
    description: "Pauses the currently playing track.",
    usage: "/pause",
    examples: ["/pause"],
    related: ["/resume"],
    preview: {
      syntax: "/pause",
      actor: { username: "Rafa", avatar: "R", color: "bg-orange-500" },
      channel: { name: "music", type: "text" },
      interaction: { input: "/pause" },
      responses: [
        {
          id: "pause_view",
          type: "embed",
          delayMs: 150,
          embed: {
            color: BRAND_PINK,
            description: "⏸️ **Música pausada.**"
          }
        }
      ]
    }
  },
  {
    name: "/resume",
    category: "Music",
    description: "Resumes the currently paused track.",
    usage: "/resume",
    examples: ["/resume"],
    related: ["/pause"],
    preview: {
      syntax: "/resume",
      actor: { username: "Rafa", avatar: "R", color: "bg-orange-500" },
      channel: { name: "music", type: "text" },
      interaction: { input: "/resume" },
      responses: [
        {
          id: "resume_view",
          type: "embed",
          delayMs: 150,
          embed: {
            color: BRAND_PINK,
            description: "▶️ **Música retomada.**"
          }
        }
      ]
    }
  },
  {
    name: "/skip",
    category: "Music",
    description: "Skips the currently playing track.",
    usage: "/skip",
    examples: ["/skip"],
    related: ["/queue", "/play"],
    preview: {
      syntax: "/skip",
      actor: { username: "Maya", avatar: "M", color: "bg-fuchsia-500" },
      channel: { name: "music", type: "text" },
      interaction: { input: "/skip" },
      responses: [
        {
          id: "skip_view",
          type: "embed",
          delayMs: 150,
          embed: {
            color: BRAND_PINK,
            description: "⏭️ **Música pulada.**"
          }
        }
      ]
    }
  },
  {
    name: "/volume",
    category: "Music",
    description: "Change Tiffany's stream volume (0–150%)",
    usage: "/volume [level]",
    examples: ["/volume 50"],
    preview: {
      syntax: "/volume 50",
      actor: { username: "Nico", avatar: "N", color: "bg-emerald-500" },
      channel: { name: "music", type: "text" },
      interaction: { input: "/volume 50" },
      responses: [
        {
          id: "response_1",
          type: "embed",
          delayMs: 150,
          embed: {
            title: "🔊 Volume",
            description: "Tiffany's **stream volume** is now **50%**.\nThis applies to **everyone** in this voice channel.",
            color: BRAND_PINK,
            fields: [
              {
                name: "🔈 Your personal volume",
                value: "**Hear Tiffany quieter/louder just for you (Discord client):**\n• **Desktop:** Right-click **Tiffany** in the voice channel → **User Volume**\n• **Mobile:** Tap **Tiffany** in the voice UI → volume icon",
                inline: false
              }
            ],
            footer: "Stream volume affects everyone in voice — client slider is just for you."
          }
        }
      ]
    }
  },
  {
    name: "/loop",
    category: "Music",
    description: "Toggle loop for the current track",
    usage: "/loop",
    examples: ["/loop"],
    preview: {
      syntax: "/loop",
      actor: { username: "Maya", avatar: "M", color: "bg-purple-500" },
      channel: { name: "music", type: "text" },
      interaction: { input: "/loop" },
      responses: [
        {
          id: "response_1",
          type: "embed",
          delayMs: 150,
          embed: {
            description: "🔁 Loop **on** — repeating: **Lofi Hip Hop Radio - Beats to Relax/Study to**",
            color: BRAND_PINK
          }
        }
      ]
    }
  },
  {
    name: "/rewind",
    category: "Music",
    description: "Your personal Tiffany Rewind!",
    usage: "/rewind",
    examples: ["/rewind"],
    preview: {
      syntax: "/rewind",
      actor: { username: "Kai", avatar: "K", color: "bg-amber-500" },
      channel: { name: "music", type: "text" },
      interaction: { input: "/rewind" },
      responses: [
        {
          id: "response_1",
          type: "embed",
          delayMs: 150,
          embed: {
            title: "🎧 Kai's Rewind",
            description: "**You requested 42 songs!**\n\n**Your top artists/channels:**\n1️⃣ **Lofi Girl** (18 plays)\n2️⃣ **ChilledCow** (12 plays)\n3️⃣ **Nujabes** (7 plays)\n",
            color: BRAND_PINK,
            footer: "Keep listening with Tiffany to update your stats!"
          }
        }
      ]
    }
  },
  {
    name: "/stats",
    category: "Music",
    description: "Is Tiffany online? Connection and available features",
    usage: "/stats",
    examples: ["/stats"],
    preview: {
      syntax: "/stats",
      actor: { username: "Alex", avatar: "A", color: "bg-blue-500" },
      channel: { name: "music", type: "text" },
      interaction: { input: "/stats" },
      responses: [
        {
          id: "response_1",
          type: "embed",
          delayMs: 150,
          embed: {
            title: "🟢 Tiffany — Running normally",
            description: "Everything looks good! 💖",
            color: GREEN,
            fields: [
              { name: "📶 Connection", value: "great (45 ms)", inline: true },
              { name: "🎵 Music & chat", value: "Available", inline: true },
              { name: "🛒 Auto deals", value: "Active", inline: true }
            ],
            footer: "Tiffany 💖 · use /updates for news"
          }
        }
      ]
    }
  },
  {
    name: "/247",
    category: "Music",
    description: "Toggle 24/7 mode in voice channel",
    usage: "/247",
    examples: ["/247"],
    preview: {
      syntax: "/247",
      actor: { username: "Luna", avatar: "L", color: "bg-indigo-500" },
      channel: { name: "music", type: "text" },
      interaction: { input: "/247" },
      responses: [
        {
          id: "response_1",
          type: "embed",
          delayMs: 150,
          embed: {
            description: "🔒 **24/7 mode on** — I won't leave for inactivity or an empty queue.",
            color: BRAND_PINK
          }
        }
      ]
    }
  },
  {
    name: "/autoplay",
    category: "Music",
    description: "Toggle autoplay",
    usage: "/autoplay",
    examples: ["/autoplay"],
    preview: {
      syntax: "/autoplay",
      actor: { username: "Rafa", avatar: "R", color: "bg-rose-500" },
      channel: { name: "music", type: "text" },
      interaction: { input: "/autoplay" },
      responses: [
        {
          id: "response_1",
          type: "embed",
          delayMs: 150,
          embed: {
            description: "▶️ **Autoplay on** — when the queue ends, I'll play similar songs.",
            color: BRAND_PINK
          }
        }
      ]
    }
  },
  {
    name: "/clear",
    category: "Music",
    description: "Stop music, clear queue, and leave voice",
    usage: "/clear",
    examples: ["/clear"],
    preview: {
      syntax: "/clear",
      actor: { username: "Nico", avatar: "N", color: "bg-emerald-500" },
      channel: { name: "music", type: "text" },
      interaction: { input: "/clear" },
      responses: [
        {
          id: "response_1",
          type: "embed",
          delayMs: 150,
          embed: {
            description: "🗑️ Queue cleared. I left the channel.",
            color: BRAND_PINK
          }
        }
      ]
    }
  },
  {
    name: "/clip",
    category: "Music",
    description: "Save the last 30 seconds of voice audio",
    usage: "/clip [fmt]",
    examples: ["/clip mp3"],
    preview: {
      syntax: "/clip mp3",
      actor: { username: "Maya", avatar: "M", color: "bg-purple-500" },
      channel: { name: "music", type: "text" },
      interaction: { input: "/clip mp3" },
      responses: [
        {
          id: "response_1",
          type: "embed",
          delayMs: 150,
          embed: {
            description: "🎬 **Clip saved!** (30s of audio, `.mp3`)",
            color: BRAND_PINK
          }
        }
      ]
    }
  },
  {
    name: "/seek",
    category: "Music",
    description: "Seek forward or backward (+30, -15, 1:30)",
    usage: "/seek [time_expr]",
    examples: ["/seek +30"],
    preview: {
      syntax: "/seek +30",
      actor: { username: "Kai", avatar: "K", color: "bg-amber-500" },
      channel: { name: "music", type: "text" },
      interaction: { input: "/seek +30" },
      responses: [
        {
          id: "response_1",
          type: "embed",
          delayMs: 150,
          embed: {
            description: "⏩ Jumping to **01:45 / 03:30**",
            color: BRAND_PINK
          }
        }
      ]
    }
  },
  {
    name: "/shuffle",
    category: "Music",
    description: "Shuffle the queue",
    usage: "/shuffle",
    examples: ["/shuffle"],
    preview: {
      syntax: "/shuffle",
      actor: { username: "Alex", avatar: "A", color: "bg-blue-500" },
      channel: { name: "music", type: "text" },
      interaction: { input: "/shuffle" },
      responses: [
        {
          id: "response_1",
          type: "embed",
          delayMs: 150,
          embed: {
            description: "🔀 Queue shuffled! (5 tracks — playing in a new order)",
            color: BRAND_PINK
          }
        }
      ]
    }
  },
  {
    name: "/replay",
    category: "Music",
    description: "Replay the current track",
    usage: "/replay",
    examples: ["/replay"],
    preview: {
      syntax: "/replay",
      actor: { username: "Luna", avatar: "L", color: "bg-indigo-500" },
      channel: { name: "music", type: "text" },
      interaction: { input: "/replay" },
      responses: [
        {
          id: "response_1",
          type: "embed",
          delayMs: 150,
          embed: {
            description: "🔄 Replaying: **Synthwave Chill Beat**",
            color: BRAND_PINK
          }
        }
      ]
    }
  },
  {
    name: "/lyrics",
    category: "Music",
    description: "Display lyrics for the current playing song.",
    usage: "/lyrics",
    examples: ["/lyrics"],
    preview: {
      syntax: "/lyrics",
      actor: { username: "Kai", avatar: "K", color: "bg-amber-500" },
      channel: { name: "music", type: "text" },
      interaction: { input: "/lyrics" },
      responses: [
        {
          id: "lyrics_view",
          type: "embed",
          delayMs: 150,
          embed: {
            color: BRAND_PINK,
            title: "🎤 Letra - Lofi Hip Hop",
            description: "(Instrumental)",
            footer: "Lyrics provided by Genius"
          }
        }
      ]
    }
  },
  {
    name: "/playlist",
    category: "Music",
    description: "Manage your personal playlists.",
    usage: "/playlist",
    examples: ["/playlist load", "/playlist save"],
    preview: {
      syntax: "/playlist load",
      actor: { username: "Luna", avatar: "L", color: "bg-indigo-500" },
      channel: { name: "music", type: "text" },
      interaction: { input: "/playlist load" },
      responses: [
        {
          id: "playlist_view",
          type: "embed",
          delayMs: 150,
          embed: {
            color: BRAND_PINK,
            title: "📂 Suas Playlists",
            description: "• **Chill Vibes** (12 tracks)\n• **Workout Mix** (24 tracks)\n• **Favorites** (150 tracks)",
          }
        }
      ]
    }
  },

  // ============================
  // AI & FUN COMMANDS
  // ============================
  {
    name: "/chat",
    category: "AI & Fun",
    description: "Ask Tiffany's AI a question. Supports image attachments.",
    usage: "/chat question:<prompt>",
    examples: ["/chat question:What is quantum computing?"],
    preview: {
      syntax: "/chat question: What is quantum computing?",
      actor: { username: "Kai", avatar: "K", color: "bg-indigo-500" },
      channel: { name: "ai-chat", type: "text" },
      interaction: { input: "/chat question: What is quantum computing?" },
      responses: [
        {
          id: "chat_thinking",
          type: "embed",
          ephemeral: true,
          delayMs: 150,
          embed: {
            color: BRAND_PINK,
            description: "💭 Tiffany está pensando...",
          }
        },
        {
          id: "chat_response",
          type: "embed",
          ephemeral: true,
          delayMs: 800,
          embed: {
            color: BRAND_PINK,
            description: "💬 Quantum computing uses quantum mechanics to process information. Unlike classical computers that use bits (0 or 1), quantum computers use quantum bits or qubits, which can exist in multiple states simultaneously (superposition). This allows them to solve certain complex problems exponentially faster than classical computers.",
          }
        }
      ]
    }
  },
  {
    name: "/game",
    category: "AI & Fun",
    description: "AI-powered game recommendations based on steam and epic stores.",
    usage: "/game prompt:<description>",
    examples: ["/game prompt:horror co-op games under $10"],
    preview: {
      syntax: "/game prompt:horror co-op games under $10",
      actor: { username: "Rafa", avatar: "R", color: "bg-rose-500" },
      channel: { name: "general", type: "text" },
      interaction: { input: "/game prompt:horror co-op games under $10" },
      responses: [
        {
          id: "game_resp",
          type: "embed",
          delayMs: 500,
          embed: {
            color: BRAND_PINK,
            title: "🎮 Game Recommendations",
            description: "Here are some horror co-op games under $10:",
            fields: [
              { name: "1. Phasmophobia", value: "Steam - $9.99\n4-player online co-op psychological horror.", inline: false },
              { name: "2. Pacify", value: "Steam - $4.99\nRun for your life in this multiplayer horror game.", inline: false }
            ]
          }
        }
      ]
    }
  },
  {
    name: "/random",
    category: "AI & Fun",
    description: "Pick a random song or item.",
    usage: "/random",
    examples: ["/random"],
    preview: {
      syntax: "/random",
      actor: { username: "Maya", avatar: "M", color: "bg-purple-500" },
      channel: { name: "general", type: "text" },
      interaction: { input: "/random" },
      responses: [
        {
          id: "random_resp",
          type: "embed",
          delayMs: 150,
          embed: {
            color: BRAND_PINK,
            description: "🎲 I picked a random song for you: **Midnight City by M83**! Adding to queue."
          }
        }
      ]
    }
  },
  {
    name: "/roleplay",
    category: "AI & Fun",
    description: "Create or edit a custom AI roleplay persona.",
    usage: "/roleplay setup",
    examples: ["/roleplay setup"],
    preview: {
      syntax: "/roleplay setup",
      actor: { username: "Alex", avatar: "A", color: "bg-blue-500" },
      channel: { name: "ai-chat", type: "text" },
      interaction: { input: "/roleplay setup" },
      responses: [
        {
          id: "rp_resp",
          type: "embed",
          delayMs: 150,
          embed: {
            color: BRAND_PINK,
            title: "🎭 AI Roleplay Setup",
            description: "Choose an AI persona for me to roleplay as in this channel.",
            fields: [
              { name: "Current Persona", value: "None (Default Tiffany)", inline: false }
            ]
          },
          components: [
            {
              type: "action_row",
              buttons: [
                { label: "Create Persona", style: "primary" },
                { label: "Select Preset", style: "secondary" }
              ]
            }
          ]
        }
      ]
    }
  },

  // ============================
  // UTILITY COMMANDS
  // ============================
  {
    name: "/mod-panel",
    category: "Utility",
    description: "Opens the interactive moderation dashboard.",
    usage: "/mod-panel",
    examples: ["/mod-panel"],
    permissions: "Administrator",
    preview: {
      syntax: "/mod-panel",
      actor: { username: "Alex", avatar: "A", color: "bg-rose-500" },
      channel: { name: "staff", type: "text" },
      interaction: { input: "/mod-panel" },
      responses: [
        {
          id: "mod_panel_view",
          type: "embed",
          ephemeral: true,
          delayMs: 150,
          embed: {
            color: BRAND_PINK,
            title: "🛠️ Painel de Moderação & Configurações",
            description: "Gerencie as configurações de segurança, canais e módulos do servidor.",
            fields: [
              { name: "🛡️ Segurança", value: "Filtro Estrito: **OFF**\nAnti-Spam: **ON**\nBlacklist: **12 palavras**", inline: true },
              { name: "⚙️ Configurações", value: "Cargo DJ: <@&1234>\nCanal Logs: <#5678>\nCanal Ofertas: `Nenhum`\nTags Afiliado: **3**", inline: true },
              { name: "🧩 Módulos", value: "Música: **ON** | AI Chat: **ON** | Sorteios: **ON**", inline: false }
            ]
          },
          components: [
            {
              type: "action_row",
              buttons: [
                { label: "Filtro Estrito", style: "danger" },
                { label: "Anti-Spam", style: "success" },
                { label: "Blacklist", style: "secondary" }
              ]
            },
            {
              type: "action_row",
              buttons: [
                { label: "Canal de Ofertas", style: "primary" },
                { label: "Módulos", style: "primary" }
              ]
            }
          ]
        }
      ]
    }
  },
  {
    name: "/updates",
    category: "Utility",
    description: "View the latest Tiffany Bot patch notes.",
    usage: "/updates",
    examples: ["/updates"],
    preview: {
      syntax: "/updates",
      actor: { username: "Nico", avatar: "N", color: "bg-emerald-500" },
      channel: { name: "general", type: "text" },
      interaction: { input: "/updates" },
      responses: [
        {
          id: "updates_resp",
          type: "embed",
          delayMs: 150,
          embed: {
            color: BRAND_PINK,
            title: "✨ Tiffany Bot v2.5",
            description: "**What's New:**\n• Improved AI response speed by 30%\n• Added new `/game` recommendation engine\n• Music system now supports 24/7 playback (Premium)"
          }
        }
      ]
    }
  },
  {
    name: "/language",
    category: "Utility",
    description: "Change the language for Tiffany responses in this server.",
    usage: "/language",
    examples: ["/language set:en"],
    permissions: "Administrator",
    preview: {
      syntax: "/language set:en",
      actor: { username: "Kai", avatar: "K", color: "bg-amber-500" },
      channel: { name: "general", type: "text" },
      interaction: { input: "/language set:en" },
      responses: [
        {
          id: "lang_resp",
          type: "embed",
          delayMs: 150,
          embed: {
            color: BRAND_PINK,
            description: "🌍 Server language updated to **English (US)**."
          }
        }
      ]
    }
  },
  {
    name: "/help",
    category: "Utility",
    description: "Display the help menu and command list.",
    usage: "/help",
    examples: ["/help"],
    preview: {
      syntax: "/help",
      actor: { username: "Luna", avatar: "L", color: "bg-indigo-500" },
      channel: { name: "general", type: "text" },
      interaction: { input: "/help" },
      responses: [
        {
          id: "help_resp",
          type: "embed",
          delayMs: 150,
          embed: {
            color: BRAND_PINK,
            title: "💖 Tiffany Bot Help",
            description: "Use the dropdown below to explore my commands by category.",
          },
          components: [
            {
              type: "action_row",
              buttons: [
                { label: "Dashboard", style: "secondary" },
                { label: "Support Server", style: "secondary" }
              ]
            }
          ]
        }
      ]
    }
  },
  {
    name: "/about",
    category: "Utility",
    description: "Bot statistics, credits, and uptime.",
    usage: "/about",
    examples: ["/about"],
    preview: {
      syntax: "/about",
      actor: { username: "Alex", avatar: "A", color: "bg-blue-500" },
      channel: { name: "general", type: "text" },
      interaction: { input: "/about" },
      responses: [
        {
          id: "about_resp",
          type: "embed",
          delayMs: 150,
          embed: {
            color: BRAND_PINK,
            title: "Tiffany Bot",
            description: "One bot for your entire server.",
            fields: [
              { name: "Servers", value: "1,245", inline: true },
              { name: "Latency", value: "24ms", inline: true },
              { name: "Uptime", value: "14 days", inline: true }
            ]
          }
        }
      ]
    }
  },

  // ============================
  // EMBEDS COMMANDS
  // ============================
  {
    name: "/embed",
    category: "Embeds",
    description: "Base command for embed creation and management.",
    usage: "/embed",
    examples: ["/embed create"],
    permissions: "Manage Messages",
  },
  {
    name: "/embed create",
    category: "Embeds",
    description: "Create a new embed interactively.",
    usage: "/embed create name:<name>",
    examples: ["/embed create name:rules"],
    permissions: "Manage Messages",
    preview: {
      syntax: "/embed create name: regras_do_servidor",
      actor: { username: "Luna", avatar: "L", color: "bg-sky-500" },
      channel: { name: "announcements", type: "text" },
      interaction: { input: "/embed create name: regras_do_servidor" },
      responses: [
        {
          id: "embed_modal",
          type: "modal",
          delayMs: 150,
          content: "Criar Embed"
        }
      ]
    }
  },
  {
    name: "/embed edit",
    category: "Embeds",
    description: "Edit an embed template",
    usage: "/embed edit <name>",
    examples: ["/embed edit rules"],
    permissions: "Manage Messages",
    preview: {
      syntax: "/embed edit name: rules",
      actor: { username: "Kai", avatar: "K", color: "bg-amber-500" },
      channel: { name: "admin-lounge", type: "text" },
      interaction: { input: "/embed edit name:rules" },
      responses: [
        {
          id: "response_1",
          type: "modal",
          delayMs: 100
        }
      ]
    }
  },
  {
    name: "/embed preview",
    category: "Embeds",
    description: "Preview an embed template",
    usage: "/embed preview <name>",
    examples: ["/embed preview rules"],
    permissions: "Manage Messages",
    preview: {
      syntax: "/embed preview name: rules",
      actor: { username: "Luna", avatar: "L", color: "bg-purple-500" },
      channel: { name: "admin-lounge", type: "text" },
      interaction: { input: "/embed preview name:rules" },
      responses: [
        {
          id: "response_1",
          type: "embed",
          delayMs: 200,
          embed: {
            title: "Server Rules",
            description: "1. Be respectful to everyone\n2. No spamming",
            color: BRAND_PINK,
            footer: "Rule updates apply automatically"
          }
        }
      ]
    }
  },
  {
    name: "/embed send",
    category: "Embeds",
    description: "Send an embed template to a channel",
    usage: "/embed send <name> [channel]",
    examples: ["/embed send rules channel:#welcome"],
    permissions: "Manage Messages",
    preview: {
      syntax: "/embed send name: rules channel: #welcome",
      actor: { username: "Rafa", avatar: "R", color: "bg-cyan-500" },
      channel: { name: "admin-lounge", type: "text" },
      interaction: { input: "/embed send name:rules channel:#welcome" },
      responses: [
        {
          id: "response_1",
          type: "embed",
          ephemeral: true,
          delayMs: 250,
          embed: {
            color: GREEN,
            description: "✅ Embed **rules** sent to <#123456>."
          }
        }
      ]
    }
  },

  // ============================
  // GIVEAWAYS COMMANDS
  // ============================
  {
    name: "/giveaway create",
    category: "Giveaways",
    description: "Start a new giveaway in the current channel.",
    usage: "/giveaway create duration:<time> winners:<count> prize:<name>",
    examples: ["/giveaway create duration:1d winners:1 prize:Discord Nitro"],
    permissions: "Manage Server",
    preview: {
      syntax: "/giveaway create duration: 1d winners: 1 prize: Discord Nitro",
      actor: { username: "Alex", avatar: "A", color: "bg-rose-500" },
      channel: { name: "giveaways", type: "text" },
      interaction: { 
        input: "/giveaway create duration: 1d winners: 1 prize: Discord Nitro" 
      },
      responses: [
        {
          id: "giveaway_confirm",
          type: "embed",
          ephemeral: true,
          delayMs: 100,
          embed: {
            color: GREEN,
            description: "✅ Sorteio de **Discord Nitro** criado com sucesso!"
          }
        },
        {
          id: "giveaway_announcement",
          type: "embed",
          delayMs: 250,
          embed: {
            color: BRAND_PINK,
            title: "🎉 Sorteio!",
            description: "**Prêmio:** Discord Nitro",
            fields: [
              { name: "Ganhadores", value: "1", inline: true },
              { name: "Participantes", value: "0", inline: true },
              { name: "Termina em", value: "em 1 dia", inline: true }
            ],
            footer: "Hosted by Alex"
          },
          components: [
            {
              type: "action_row",
              buttons: [
                { label: "Participar", style: "success", emoji: "🎉" }
              ]
            }
          ]
        }
      ]
    }
  },
  {
    name: "/giveaway end",
    category: "Giveaways",
    description: "End a giveaway early and pick winners",
    usage: "/giveaway end [gw_id]",
    examples: ["/giveaway end"],
    permissions: "Manage Server",
    preview: {
      syntax: "/giveaway end gw_id: a1b2c3d4e5f6",
      actor: { username: "Alex", "avatar": "A", "color": "bg-rose-500" },
      channel: { name: "general", type: "text" },
      interaction: { input: "/giveaway end gw_id:a1b2c3d4e5f6" },
      responses: [
        {
          id: "response_1",
          type: "embed",
          delayMs: 150,
          embed: {
            title: "🎉 Giveaway ended!",
            description: "Winner(s): <@123456789012345678>",
            color: BRAND_PINK
          }
        }
      ]
    }
  },
  {
    name: "/giveaway list",
    category: "Giveaways",
    description: "List active giveaways on this server",
    usage: "/giveaway list",
    examples: ["/giveaway list"],
    preview: {
      syntax: "/giveaway list",
      actor: { username: "Nico", avatar: "N", color: "bg-indigo-500" },
      channel: { name: "general", type: "text" },
      interaction: { input: "/giveaway list" },
      responses: [
        {
          id: "response_1",
          type: "embed",
          delayMs: 150,
          embed: {
            title: "🎁 Active giveaways",
            description: "• `a1b2c3d4e5f6` — **VIP Rank** · 5 entries · 1h 45m",
            color: BRAND_PINK
          }
        }
      ]
    }
  },
  {
    name: "/giveaway reroll",
    category: "Giveaways",
    description: "Reroll winners from an ended giveaway",
    usage: "/giveaway reroll [gw_id]",
    examples: ["/giveaway reroll"],
    permissions: "Manage Server",
    preview: {
      syntax: "/giveaway reroll gw_id: a1b2c3d4e5f6",
      actor: { username: "Maya", avatar: "M", color: "bg-emerald-500" },
      channel: { name: "general", type: "text" },
      interaction: { input: "/giveaway reroll gw_id:a1b2c3d4e5f6" },
      responses: [
        {
          id: "response_1",
          type: "embed",
          delayMs: 150,
          embed: {
            title: "🔄 Reroll",
            description: "New winner(s): <@987654321098765432>",
            color: BRAND_PINK
          }
        }
      ]
    }
  }
];
