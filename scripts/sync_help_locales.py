#!/usr/bin/env python3
"""Strip stale help.* from bot.json and sync help.json music bodies from catalog."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCALES = ROOT / "locales"

HELP_KEYS = frozenset({
    "help.title", "help.desc", "help.music.title", "help.music.body",
    "help.chat.title", "help.chat.body", "help.dice.title", "help.dice.body",
    "help.settings.title", "help.settings.body", "help.footer",
})

MUSIC_BY_LANG = {
    "tr": (
        "`/play` — ses kanalında çal · `/skip` — parçayı atla · `/pause` — duraklat · `/resume` — devam\n\n"
        "`/queue` — kuyruk + çalan parça · `/shuffle` — karıştır · `/loop` — tekrar · `/replay` — baştan çal\n\n"
        "`/random` — rastgele hit (10k) · `/autoplay` — autoplay · `/lyrics` — şarkı sözü · `/seek` — +30 / -15\n\n"
        "`/volume` — stream sesi (t!v) · `/clear` — durdur ve çık · `/nonstop` — 24/7 · `/clip` — son 30sn · `/playlist` — listeler"
    ),
    "sv": (
        "`/play` — spela i röst · `/skip` — hoppa över · `/pause` — pausa · `/resume` — fortsätt\n\n"
        "`/queue` — kö + spelas nu · `/shuffle` — blanda · `/loop` — loop · `/replay` — spela om\n\n"
        "`/random` — slumpmässig hit (10k) · `/autoplay` — autoplay · `/lyrics` — text · `/seek` — +30 / -15\n\n"
        "`/volume` — streamvolym (t!v) · `/clear` — stoppa & lämna · `/nonstop` — 24/7 · `/clip` — sista 30s · `/playlist` — listor"
    ),
    "it": (
        "`/play` — musica in voce · `/skip` — salta brano · `/pause` — pausa · `/resume` — riprendi\n\n"
        "`/queue` — coda + in riproduzione · `/shuffle` — mescola · `/loop` — loop · `/replay` — riavvia brano\n\n"
        "`/random` — hit casuale (10k) · `/autoplay` — autoplay · `/lyrics` — testo · `/seek` — +30 / -15\n\n"
        "`/volume` — volume stream (t!v) · `/clear` — stop & esci · `/nonstop` — 24/7 · `/clip` — ultimi 30s · `/playlist` — playlist"
    ),
    "nl": (
        "`/play` — muziek in voice · `/skip` — overslaan · `/pause` — pauze · `/resume` — hervatten\n\n"
        "`/queue` — wachtrij + now playing · `/shuffle` — shuffle · `/loop` — loop · `/replay` — opnieuw\n\n"
        "`/random` — random hit (10k) · `/autoplay` — autoplay · `/lyrics` — lyrics · `/seek` — +30 / -15\n\n"
        "`/volume` — streamvolume (t!v) · `/clear` — stop & leave · `/nonstop` — 24/7 · `/clip` — laatste 30s · `/playlist` — lijsten"
    ),
    "ar": (
        "`/play` — موسيقى في الصوت · `/skip` — تخطّي · `/pause` — إيقاف مؤقت · `/resume` — استئناف\n\n"
        "`/queue` — الطابور + يُشغَّل الآن · `/shuffle` — خلط · `/loop` — تكرار · `/replay` — إعادة\n\n"
        "`/random` — hit عشوائي (10k) · `/autoplay` — autoplay · `/lyrics` — كلمات · `/seek` — +30 / -15\n\n"
        "`/volume` — صوت stream (t!v) · `/clear` — إيقاف ومغادرة · `/nonstop` — 24/7 · `/clip` — آخر 30ث · `/playlist` — قوائم"
    ),
    "ja": (
        "`/play` — ボイスで再生 · `/skip` — スキップ · `/pause` — 一時停止 · `/resume` — 再開\n\n"
        "`/queue` — キュー + 再生中 · `/shuffle` — シャッフル · `/loop` — ループ · `/replay` — 最初から\n\n"
        "`/random` — ランダム曲 (10k) · `/autoplay` — 自動再生 · `/lyrics` — 歌詞 · `/seek` — +30 / -15\n\n"
        "`/volume` — 音量 (t!v) · `/clear` — 停止して退出 · `/nonstop` — 24/7 · `/clip` — 直近30秒 · `/playlist` — プレイリスト"
    ),
    "ko": (
        "`/play` — 보이스 재생 · `/skip` — 건너뛰기 · `/pause` — 일시정지 · `/resume` — 재개\n\n"
        "`/queue` — 대기열 + 재생 중 · `/shuffle` — 셔플 · `/loop` — 반복 · `/replay` — 처음부터\n\n"
        "`/random` — 무작위 히트 (10k) · `/autoplay` — 자동재생 · `/lyrics` — 가사 · `/seek` — +30 / -15\n\n"
        "`/volume` — 스트림 볼륨 (t!v) · `/clear` — 중지 후 퇴장 · `/nonstop` — 24/7 · `/clip` — 최근 30초 · `/playlist` — 플레이리스트"
    ),
    "ru": (
        "`/play` — музыка в войсе · `/skip` — пропустить · `/pause` — пауза · `/resume` — продолжить\n\n"
        "`/queue` — очередь + сейчас · `/shuffle` — перемешать · `/loop` — повтор · `/replay` — сначала\n\n"
        "`/random` — случайный хит (10k) · `/autoplay` — autoplay · `/lyrics` — текст · `/seek` — +30 / -15\n\n"
        "`/volume` — громкость (t!v) · `/clear` — стоп и выход · `/nonstop` — 24/7 · `/clip` — последние 30с · `/playlist` — плейлисты"
    ),
    "hi": (
        "`/play` — वॉइस में बजाएँ · `/skip` — स्किप · `/pause` — रोकें · `/resume` — फिर चलाएँ\n\n"
        "`/queue` — कतार + अभी बज रहा · `/shuffle` — शफल · `/loop` — लूप · `/replay` — शुरू से\n\n"
        "`/random` — रैंडम हिट (10k) · `/autoplay` — autoplay · `/lyrics` — lyrics · `/seek` — +30 / -15\n\n"
        "`/volume` — स्ट्रीम वॉल्यूम (t!v) · `/clear` — रोकें और छोड़ें · `/nonstop` — 24/7 · `/clip` — अंतिम 30s · `/playlist` — प्लेलिस्ट"
    ),
    "vi": (
        "`/play` — phát trong voice · `/skip` — bỏ qua · `/pause` — tạm dừng · `/resume` — tiếp tục\n\n"
        "`/queue` — hàng đợi + đang phát · `/shuffle` — xáo trộn · `/loop` — lặp · `/replay` — phát lại từ đầu\n\n"
        "`/random` — hit ngẫu nhiên (10k) · `/autoplay` — autoplay · `/lyrics` — lời bài hát · `/seek` — +30 / -15\n\n"
        "`/volume` — âm lượng stream (t!v) · `/clear` — dừng & rời voice · `/nonstop` — 24/7 · `/clip` — 30 giây cuối · `/playlist` — playlist"
    ),
    "uk": (
        "`/play` — музика у голосовому · `/skip` — пропустити · `/pause` — пауза · `/resume` — продовжити\n\n"
        "`/queue` — черга + зараз грає · `/shuffle` — перемішати · `/loop` — повтор · `/replay` — з початку\n\n"
        "`/random` — випадковий хіт (10k) · `/autoplay` — autoplay · `/lyrics` — текст · `/seek` — +30 / -15\n\n"
        "`/volume` — гучність (t!v) · `/clear` — стоп і вихід · `/nonstop` — 24/7 · `/clip` — останні 30с · `/playlist` — плейлисти"
    ),
}


def main() -> int:
    catalog = json.loads((LOCALES / "_catalog_en.json").read_text(encoding="utf-8"))
    en_music = catalog["help.music.body"]

    for bot_path in LOCALES.glob("*/bot.json"):
        data = json.loads(bot_path.read_text(encoding="utf-8"))
        removed = [k for k in list(data) if k in HELP_KEYS]
        if not removed:
            continue
        for k in removed:
            del data[k]
        bot_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"stripped {len(removed)} keys from {bot_path.relative_to(ROOT)}")

    for help_path in LOCALES.glob("*/help.json"):
        lang = help_path.parent.name
        data = json.loads(help_path.read_text(encoding="utf-8"))
        data["help.music.body"] = MUSIC_BY_LANG.get(lang, en_music)
        if lang == "hi":
            data["help.footer"] = (
                "🎙️ वॉइस में: «Tiffany, play [song]» · skip · pause · queue\n\n"
                "YouTube · Spotify · Deezer · Apple Music · Amazon Music\n\n"
                "🌐 **`/language`** — 16 भाषाएँ: EN · PT · ES · FR · DE · TR · SV · IT · NL · AR · JA · KO · RU · HI · VI · UK"
            )
        help_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"updated {help_path.relative_to(ROOT)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
