import spotifyService from '../services/spotify.js';
import soundcloudService from '../services/soundcloud.js';
import { cache } from '../utils/cache.js';

export async function searchTrack(lavalink, query, requester) {
  const cached = cache.get(query);
  if (cached) {
    console.log(`[Search] Cache hit: ${query}`);
    return { ...cached, requester };
  }

  let trackUrl = null;
  let metadata = null;

  // 1. Detecta Spotify
  if (query.includes('spotify.com/track')) {
    console.log('[Search] Spotify URL detectada');
    metadata = await spotifyService.getMetadata(query);
    if (metadata) {
      // Busca no SoundCloud primeiro
      trackUrl = await soundcloudService.search(`${metadata.title} ${metadata.artist}`);
      // Fallback: Lavalink YouTube search
      if (!trackUrl) {
        trackUrl = `ytsearch:${metadata.title} ${metadata.artist}`;
      }
    }
  } else {
    // 2. SoundCloud primeiro
    console.log(`[Search] Buscando no SoundCloud: ${query}`);
    trackUrl = await soundcloudService.search(query);
    
    // 3. Fallback: Lavalink YouTube search (formato ytsearch:query)
    if (!trackUrl) {
      console.log(`[Search] SoundCloud falhou, usando Lavalink YouTube search: ${query}`);
      trackUrl = `ytsearch:${query}`;
    }
  }

  if (!trackUrl) {
    console.error(`[Search] Nenhuma fonte encontrada para: ${query}`);
    return null;
  }

  console.log(`[Search] Carregando no Lavalink: ${typeof trackUrl === 'string' ? trackUrl : trackUrl.url}`);

  try {
    // Carrega faixa no Lavalink (se for string, é busca ytsearch:)
    const urlToLoad = typeof trackUrl === 'string' ? trackUrl : trackUrl.url;
    const loadResult = await lavalink.rest.loadTracks(urlToLoad);
    
    console.log(`[Search] Lavalink load result: ${loadResult.loadType}`);
    
    let lavalinkTrack = null;
    
    if (loadResult.loadType === 'track') {
      lavalinkTrack = loadResult.data;
    } else if (loadResult.loadType === 'search') {
      // Lavalink retornou lista de busca
      if (loadResult.data && loadResult.data.length > 0) {
        lavalinkTrack = loadResult.data[0];
      }
    }
    
    if (!lavalinkTrack) {
      console.error('[Search] Lavalink não retornou faixa válida');
      return null;
    }

    const result = {
      title: lavalinkTrack.info.title,
      author: lavalinkTrack.info.author,
      duration: lavalinkTrack.info.length,
      track: lavalinkTrack.track,
      thumbnail: lavalinkTrack.info.artworkUrl || (typeof trackUrl === 'object' ? trackUrl.thumbnail : null) || 'https://i.imgur.com/2W3ZxXJ.png',
      url: lavalinkTrack.info.uri,
      requester
    };

    cache.set(query, result, 3600);
    console.log(`[Search] Faixa carregada: ${result.title}`);
    return result;
  } catch (error) {
    console.error('[Search] Erro ao carregar faixa no Lavalink:', error);
    return null;
  }
}
