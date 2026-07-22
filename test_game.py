import asyncio
import aiohttp
import json
import game_recommendations as gr

class MockAI:
    pass

from dotenv import load_dotenv
load_dotenv()

async def main():
    import tiffany_voice
    ai = tiffany_voice._get_openrouter_client()
    async with aiohttp.ClientSession() as session:
        resp = await ai.chat.completions.create(
            model="google/gemini-3.1-flash-lite",
            messages=[
                {"role": "system", "content": gr._RECOMMEND_SYSTEM},
                {"role": "user", "content": 'horror, 30 reais, multiplayer, steam e epic'},
            ],
            response_format={"type": "json_object"},
            max_tokens=420,
            temperature=0.25,
            timeout=25.0,
        )
        print("FILTERS:", gr._filters_from_json(json.loads(resp.choices[0].message.content)))
        print("GAMES:", gr._parse_game_names(json.loads(resp.choices[0].message.content)))

        matches, flt, err = await gr.recommend_games('horror, 30 reais, multiplayer, steam e epic', ai)
        print("MATCHES:", len(matches))
        for r in matches:
            print(r)

asyncio.run(main())
