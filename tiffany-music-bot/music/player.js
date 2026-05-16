import { queueManager } from './queue.js';
import { searchTrack } from './search.js';

export async function playTrack(client, guildId, voiceChannel, textChannel, requester, query) {
  const lavalink = client.lavalink;
  
  // Verifica se Lavalink está conectado
  if (!lavalink || !lavalink.nodes.first()?.connected) {
    textChannel.send('❌ Lavalink não está conectado! Verifique se o serviço está rodando.');
    console.error('Lavalink não conectado. Nodes:', lavalink?.nodes);
    return;
  }

  let player = lavalink.players.get(guildId);
  if (!player) {
    player = lavalink.createPlayer(guildId);
  }

  // Entra no canal de voz
  try {
    if (!player.connected) {
      console.log(`Conectando ao canal de voz: ${voiceChannel.id}`);
      await player.connect(voiceChannel.id, { deaf: true });
      console.log('Conectado ao canal de voz com sucesso');
    }
  } catch (error) {
    console.error('Erro ao conectar no canal de voz:', error);
    textChannel.send('❌ Erro ao entrar no canal de voz!');
    return;
  }

  // Busca a música
  console.log(`Buscando música: ${query}`);
  const track = await searchTrack(lavalink, query, requester);
  
  if (!track) {
    textChannel.send('❌ Nenhuma faixa encontrada! Tente outro termo.');
    console.error(`Nenhuma faixa encontrada para: ${query}`);
    return;
  }

  console.log(`Faixa encontrada: ${track.title}`);

  const queue = queueManager.getQueue(guildId);
  
  if (player.playing || player.paused) {
    queueManager.addTrack(guildId, track);
    textChannel.send(`✅ Adicionado à fila: **${track.title}**`);
  } else {
    try {
      player.play(track.track);
      player.setTextChannel(textChannel.id);
      queue.current = track;
      console.log(`Tocando: ${track.title}`);
    } catch (error) {
      console.error('Erro ao tocar faixa:', error);
      textChannel.send('❌ Erro ao iniciar reprodução!');
    }
  }
}
