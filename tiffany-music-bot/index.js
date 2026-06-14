import { Client, Collection } from 'discord.js';
import { Lavaclient } from '@lavaclient/core';
import { DiscordJSClientPlugin } from '@lavaclient/discord.js';
import dotenv from 'dotenv';
import fs from 'fs';
import path from 'path';
import queueManager from './music/queue.js';
import { formatDuration } from './utils/format.js';

dotenv.config();

const client = new Client({
  intents: ['Guilds', 'GuildVoiceStates', 'GuildMessages', 'MessageContent']
});

client.commands = new Collection();
const leaveTimeouts = new Map();

// Carrega comandos
const commandsPath = path.join(path.resolve(), 'commands');
const commandFiles = fs.readdirSync(commandsPath).filter(file => file.endsWith('.js'));

for (const file of commandFiles) {
  const filePath = path.join(commandsPath, file);
  const command = (await import(filePath)).default;
  client.commands.set(command.data.name, command);
}

// Lavalink
client.lavalink = new Lavaclient({
  nodes: [{
    host: process.env.LAVALINK_HOST || '127.0.0.1',
    port: parseInt(process.env.LAVALINK_PORT || '2333'),
    password: process.env.LAVALINK_PASSWORD || 'youshallnotpass',
    id: 'main-node'
  }],
  plugins: [new DiscordJSClientPlugin(client)],
  sendGatewayPayload: (client, payload) => client.ws.send(payload)
});

// Eventos Lavalink
client.lavalink.on('nodeReady', (node) => console.log(`✅ Lavalink ${node.id} conectado`));
client.lavalink.on('nodeError', (node, error) => console.error(`❌ Lavalink erro:`, error));

client.lavalink.on('trackStart', (player, track) => {
  const channel = client.channels.cache.get(player.textChannelId);
  if (!channel) return;
  channel.send({ embeds: [{
    title: `🎶 Tocando agora: ${track.title}`,
    description: `Por: ${track.author}`,
    thumbnail: { url: track.thumbnail || 'https://i.imgur.com/2W3ZxXJ.png' },
    fields: [
      { name: 'Duração', value: formatDuration(track.duration), inline: true },
      { name: 'Solicitado por', value: `<@${track.requester.id}>`, inline: true }
    ],
    color: 0x1DB954
  }] });
});

client.lavalink.on('trackEnd', (player) => {
  const queue = queueManager.getQueue(player.guildId);
  const nextTrack = queueManager.nextTrack(player.guildId);
  if (nextTrack) {
    player.play(nextTrack.track);
    queue.current = nextTrack;
  } else {
    player.disconnect();
    queueManager.clearQueue(player.guildId);
  }
});

client.lavalink.on('trackError', (player, track, error) => {
  console.error('Erro na faixa:', error);
  const channel = client.channels.cache.get(player.textChannelId);
  channel?.send(`❌ Erro ao reproduzir **${track.title}**`);
});

// Silencioso: sai após 5 min se canal vazio (sem avisos)
client.on('voiceStateUpdate', (oldState, newState) => {
  const guild = oldState.guild;
  const player = client.lavalink.players.get(guild.id);
  if (!player) return;

  const voiceChannel = guild.members.cache.get(client.user.id)?.voice.channel;
  if (!voiceChannel) return;

  const nonBotMembers = voiceChannel.members.filter(m => !m.user.bot);

  if (nonBotMembers.size === 0) {
    if (!leaveTimeouts.has(guild.id)) {
      const timeout = setTimeout(() => {
        const currentChannel = guild.members.cache.get(client.user.id)?.voice.channel;
        if (currentChannel) {
          const members = currentChannel.members.filter(m => !m.user.bot);
          if (members.size === 0) {
            player.disconnect();
            queueManager.clearQueue(guild.id);
          }
        }
        leaveTimeouts.delete(guild.id);
      }, 5 * 60 * 1000);
      leaveTimeouts.set(guild.id, timeout);
    }
  } else {
    if (leaveTimeouts.has(guild.id)) {
      clearTimeout(leaveTimeouts.get(guild.id));
      leaveTimeouts.delete(guild.id);
    }
  }
});

// Eventos Discord
client.once('ready', async () => {
  console.log(`✅ Bot logado como ${client.user.tag}`);
  await client.lavalink.start(client.user.id);
});

client.on('messageCreate', async (message) => {
  if (!message.content.startsWith('t!') || message.author.bot) return;
  const contentAfterPrefix = message.content.slice(2).trim();
  if (!contentAfterPrefix) return;
  const [commandName, ...args] = contentAfterPrefix.split(/\s+/);
  const command = client.commands.get(commandName.toLowerCase());
  if (!command) return;

  try {
    await command.execute(message, args, client);
  } catch (error) {
    console.error(error);
    message.reply('❌ Erro ao executar o comando!').catch(() => {});
  }
});

client.login(process.env.DISCORD_TOKEN);
