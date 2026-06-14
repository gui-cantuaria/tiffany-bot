import yt_dlp

for client in ['ios', 'android', 'web', 'tv_embedded']:
    print(f'\n--- Testando client: {client} ---')
    opts = {
        'proxy': 'socks5://127.0.0.1:40000',
        'cookiefile': 'cookies.txt',
        'format': 'bestaudio/best',
        'quiet': True,
        'no_warnings': True,
        'extractor_args': {'youtube': {'player_client': [client]}},
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info('https://www.youtube.com/watch?v=4NRXx6U8ABQ', download=False)
            if info:
                fmt = info.get('format', 'desconhecido')
                print(f'OK: {info.get("title")} (formato: {fmt})')
            else:
                print('FALHOU: sem info')
    except Exception as e:
        print(f'ERRO: {str(e)[:150]}')
