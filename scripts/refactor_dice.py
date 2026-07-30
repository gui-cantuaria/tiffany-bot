import os

def do_refactor():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    tiffany_path = os.path.join(base_dir, "tiffany_voice.py")
    cog_path = os.path.join(base_dir, "cogs", "dice_cog.py")
    
    with open(tiffany_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
        
    start_idx = 6381 - 1
    end_idx = 7218 - 1
    
    dice_lines = lines[start_idx:end_idx + 1]
    
    # Write to dice_cog.py with some basic scaffolding
    os.makedirs(os.path.dirname(cog_path), exist_ok=True)
    with open(cog_path, "w", encoding="utf-8") as f:
        f.write('"""Dice rolling and RPG macro system."""\n')
        f.write("import discord\n")
        f.write("from discord.ext import commands\n")
        f.write("import re\n")
        f.write("import os\n")
        f.write("import json\n")
        f.write("import logging\n")
        f.write("import asyncio\n")
        f.write("import time\n")
        f.write("from typing import Optional\n")
        f.write("import guild_config\n")
        f.write("import locale_utils\n")
        f.write("from locale_utils import tr, interaction_lang, resolve_lang\n")
        f.write("from utils import _embed\n")
        f.write("\n")
        f.write("log = logging.getLogger('tiffany-bot')\n\n")
        
        # We need to indent the methods that were inside register_voice if we make them Cog methods.
        # But wait, some are just global functions. We can just dump them.
        for line in dice_lines:
            f.write(line)
            
    # Now remove from tiffany_voice.py
    new_tiffany = lines[:start_idx] + ["\n# Dice logic has been moved to cogs.dice_cog\n"] + lines[end_idx+1:]
    
    # We also need to remove `_load_dice_macros()` and `bot.add_view(DiceRerollView())` from register_voice
    # They are around line 7094. Since we shifted indices, we must just search for them.
    for i in range(len(new_tiffany)):
        if "    _load_dice_macros()" in new_tiffany[i]:
            new_tiffany[i] = ""
        elif "    bot.add_view(DiceRerollView())" in new_tiffany[i]:
            new_tiffany[i] = ""
            
    with open(tiffany_path, "w", encoding="utf-8") as f:
        f.writelines(new_tiffany)
        
    print("Dice logic extracted to cogs/dice_cog.py and removed from tiffany_voice.py")

if __name__ == "__main__":
    do_refactor()
