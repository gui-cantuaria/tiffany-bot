import playDl from 'play-dl';

export default {
  async search(query) {
    try {
      console.log(`[YouTube] Buscando: ${query}`);
      
      // play-dl retorna array de resultados
      const results = await playDl.search(query, { 
        source: 'ytsearch', 
        limit: 1
      });
      
      if (!results || results.length === 0) {
        console.log('[YouTube] Nenhum resultado');
        return null;
      }
      
      const track = results[0];
      console.log(`[YouTube] Encontrado: ${track.title}`);
      console.log(`[YouTube] URL: ${track.url}`);
      
      // play-dl deve retornar URL completa do vídeo
      if (!track.url || !track.url.includes('youtube.com')) {
        console.error('[YouTube] URL inválida:', track.url);
        return null;
      }
      
      return {
        url: track.url, // Deve ser https://www.youtube.com/watch?v=XXXX
        thumbnail: track.thumbnail?.url || null
      };
    } catch (error) {
      console.error('[YouTube] Erro:', error.message);
      return null;
    }
  }
};
