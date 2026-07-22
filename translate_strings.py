import os
import re
import json
import urllib.request
import locale_utils
from pprint import pformat
import subprocess

API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
URL = "https://openrouter.ai/api/v1/chat/completions"

def translate_text(en_text: str) -> dict:
    prompt = f"Translate the following Discord bot text to French and German. Preserve the exact markdown formatting (**), variables (like {{guild}} or {{track}}), and newlines. Return ONLY a JSON object with 'fr' and 'de' keys. Text:\n{en_text}"
    data = {
        "model": "openai/gpt-4o-mini",
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"}
    }
    req = urllib.request.Request(URL, json.dumps(data).encode("utf-8"), headers={
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    })
    
    try:
        with urllib.request.urlopen(req) as response:
            res = json.loads(response.read().decode())
            parsed = json.loads(res['choices'][0]['message']['content'])
            return parsed
    except Exception as e:
        print(f"Error translating '{en_text}': {e}")
        return {"fr": "", "de": ""}

def main():
    strings = locale_utils._STRINGS
    count = 0
    for key, langs in strings.items():
        needs_fr = "fr" not in langs or not langs["fr"]
        needs_de = "de" not in langs or not langs["de"]
        
        if needs_fr or needs_de:
            en_text = langs.get("en", "")
            if en_text:
                print(f"Translating: {key}")
                translated = translate_text(en_text)
                if needs_fr and "fr" in translated and translated["fr"]:
                    langs["fr"] = translated["fr"]
                if needs_de and "de" in translated and translated["de"]:
                    langs["de"] = translated["de"]
                count += 1
                
    if count == 0:
        print("No missing translations found.")
        return

    # Read locale_utils.py to replace just the _STRINGS assignment
    with open("locale_utils.py", "r", encoding="utf-8") as f:
        content = f.read()

    # The assignment starts with _STRINGS: dict[str, dict[GuildLang, str]] = {
    # and ends at the end of the file or before something else.
    # We can just replace the whole file content after _STRINGS
    start_str = "_STRINGS: dict[str, dict[GuildLang, str]] = {"
    start_idx = content.find(start_str)
    
    if start_idx == -1:
        print("Could not find _STRINGS assignment in locale_utils.py")
        return
        
    before_strings = content[:start_idx]
    
    formatted_dict = pformat(strings, indent=4, width=120)
    
    new_content = before_strings + "_STRINGS: dict[str, dict[GuildLang, str]] = " + formatted_dict + "\n"
    
    with open("locale_utils.py", "w", encoding="utf-8") as f:
        f.write(new_content)
        
    print("Rewrote locale_utils.py. Running black...")
    subprocess.run(["py", "-m", "black", "locale_utils.py", "-l", "140"])
    print("Done!")

if __name__ == "__main__":
    main()
