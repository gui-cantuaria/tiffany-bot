# Tiffany Bot — Top.gg (English)

Native English copy for the Top.gg listing. HTML + inline CSS supported on long descriptions.

---

## Before publishing

Replace placeholders in the HTML:

| Placeholder | Where to find |
|---|---|
| `REPLACE_CLIENT_ID` | Discord Developer Portal → your app → **Application ID** |
| `REPLACE_BOT_ID` | Top.gg bot page URL: `top.gg/bot/123456789` → use `123456789` |

Invite link uses Tiffany's permission set (voice + messages + embeds + manage messages).

---

1. [top.gg](https://top.gg) → your bot → **Edit**
2. **Short description** → paste from `topgg-shortdesc.txt` (under 140 characters)
3. **Long description** → open `topgg-description.html`, copy everything from the first `<div style=...>` to the closing `</div>`, paste into the editor
4. Preview → Save

**Portuguese listing:** use `topgg-description-pt.html` for the `pt` locale.

---

## Short description (EN)

```
Your all-in-one Discord bot: music, AI chat, game picks, RPG dice & scam protection. Try /play or /help!
```

---

## Files

| File | Purpose |
|---|---|
| `topgg-description.html` | Long description — **fluent English** (primary) |
| `topgg-description-pt.html` | Long description — PT-BR locale |
| `topgg-shortdesc.txt` | Short description (140 chars max) |

---

## Suggested tags

`Music` · `Moderation` · `Fun` · `Utility` · `Games` · `AI`

## Banner

960×540 · dark background · accent `#FF69B4` · logo + “Music · Games · AI”
