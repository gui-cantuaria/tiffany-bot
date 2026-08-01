<div align="center">
  <h1>🤖 Tiffany Bot</h1>
  <p><strong>A powerful, multifunctional, and resilient Discord Bot built with Python.</strong></p>
  
  <p>
    <img src="https://img.shields.io/badge/Python-3.11+-blue.svg" alt="Python Version" />
    <img src="https://img.shields.io/badge/Discord.py-2.4+-blue.svg" alt="Discord.py" />
    <img src="https://img.shields.io/badge/License-MIT-green.svg" alt="License" />
  </p>
</div>

---

Tiffany is a self-hosted, highly customizable Discord bot designed to enrich your server experience. Whether you need high-quality music playback, AI-powered conversational capabilities, tabletop RPG dice rolling, or automated tech news and deal alerts, Tiffany has you covered.

Built with resilience in mind, Tiffany supports both modern Slash Commands (`/`) and traditional Prefix Commands (`t!`), adapting perfectly to any community's workflow.

## ✨ Key Features

🎶 **Advanced Music System**
- High-quality audio playback
- Full queue management, shuffle, loop, and autoplay
- Support for playlists and on-demand lyrics
- Volume control and audio manipulation

🧠 **AI Integration & Chat**
- Natural conversational AI powered by cutting-edge models
- Deep roleplay capabilities
- Automatic web link summarization
- Personalized game recommendations

🎲 **Tabletop & Dice**
- Robust dice rolling system
- Custom dice macros saved directly to chat

📰 **Automated Feeds (Optional)**
- **Tech News:** Curated RSS post delivery to keep your server informed.
- **Deal Alerts:** Real-time offer alerts broadcasted to dedicated channels.

🌍 **Multilingual Support**
- Full support for **16 languages**.
- Seamless per-user language preference via the `/language` command.

## 🛠️ Prerequisites

Before you begin, ensure you have met the following requirements:
* **Python 3.11** or higher.
* A registered **Discord Bot Token** from the [Discord Developer Portal](https://discord.com/developers/applications).
* **FFmpeg** installed on your system (required for the music module).

## 🚀 Installation & Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/gui-cantuaria/tiffany-bot.git
   cd tiffany-bot
   ```

2. **Install dependencies:**
   It is highly recommended to use a virtual environment.
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows use: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Configuration:**
   Copy the example environment file and populate it with your credentials.
   ```bash
   cp .env.example .env
   ```
   Open `.env` and fill in your `DISCORD_TOKEN` and other preferred configurations.

4. **Launch the Bot:**
   Start the bot using the robust launcher which handles auto-restarts and graceful shutdowns.
   ```bash
   python launcher.py
   ```

## ⚙️ Configuration (.env)

The bot relies heavily on the `.env` file to toggle modules and configure APIs. Ensure you read through `.env.example` to understand how to turn features like News and Deals on or off, and where to place your AI API keys.

## 🤝 Contributing

We welcome contributions from the open-source community! If you'd like to improve Tiffany, please follow these steps:

> **Boundary notice:** This repository contains both the production **Tiffany Bot** (Discord integration) and the experimental **Tiffany OS Core** (`tiffany_core/`, private-boundary intelligence). See [`docs/open-ecosystem-strategy.md`](docs/open-ecosystem-strategy.md) before contributing to core platform code.

1. Fork the project.
2. Create your feature branch (`git checkout -b feature/AmazingFeature`).
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`).
4. Push to the branch (`git push origin feature/AmazingFeature`).
5. Open a Pull Request.

Please read our [CONTRIBUTING.md](CONTRIBUTING.md) for details on our code of conduct and the process for submitting pull requests.

## 📝 License

Distributed under the MIT License. See `LICENSE` for more information.

---
<div align="center">
  <i>Made with ❤️ for the Discord community.</i>
</div>
