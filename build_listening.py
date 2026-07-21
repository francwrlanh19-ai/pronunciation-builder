#!/usr/bin/env python3
"""
Converte os exercicios escritos em public/listening/fontes/*.json
em audio (.mp3) + exercicio final (.json) + catalogo (index.json).

Roda dentro do GitHub Actions. Nao usa nenhuma API paga:
o audio vem do Edge TTS, que e gratuito.

So processa o que ainda nao tem audio, entao rodar de novo e barato.
Use --forcar para regerar tudo.
"""

import argparse
import asyncio
import json
import sys
import unicodedata
import re
from datetime import datetime
from pathlib import Path

try:
    import edge_tts
except ImportError:
    sys.exit("Falta a lib edge-tts. No Actions isso e instalado pelo workflow.")


PASTA = Path("public/listening")
FONTES = PASTA / "fontes"

# Velocidade da fala por nivel. Negativo = mais devagar que o normal.
RATE_POR_NIVEL = {
    "A1": "-30%",
    "A2": "-20%",
    "B1": "-10%",
    "B2": "+0%",
    "C1": "+10%",
}

# Quantas palavras por minuto cada nivel escuta confortavelmente.
WPM_POR_NIVEL = {"A1": 100, "A2": 120, "B1": 140, "B2": 160, "C1": 175}

VOZES = {
    "us_f": "en-US-AriaNeural",
    "us_m": "en-US-GuyNeural",
    "uk_f": "en-GB-SoniaNeural",
    "uk_m": "en-GB-RyanNeural",
    "au_f": "en-AU-NatashaNeural",
    "no_f": "nb-NO-PernilleNeural",
    "no_m": "nb-NO-FinnNeural",
}

VOZ_PADRAO = "us_f"


def slug(texto):
    texto = unicodedata.normalize("NFKD", texto)
    texto = texto.encode("ascii", "ignore").decode("ascii")
    texto = re.sub(r"[^\w\s-]", "", texto).strip().lower()
    return re.sub(r"[-\s]+", "-", texto)[:40]


def validar(fonte, caminho):
    """Devolve uma lista de problemas. Lista vazia = arquivo ok."""
    problemas = []

    for campo in ("titulo", "nivel", "transcript", "perguntas"):
        if not fonte.get(campo):
            problemas.append(f"falta o campo '{campo}'")

    if problemas:
        return problemas

    if fonte["nivel"] not in RATE_POR_NIVEL:
        problemas.append(f"nivel '{fonte['nivel']}' invalido — use A1, A2, B1, B2 ou C1")

    if not isinstance(fonte["perguntas"], list) or not fonte["perguntas"]:
        problemas.append("'perguntas' precisa ser uma lista nao vazia")
        return problemas

    for i, p in enumerate(fonte["perguntas"], 1):
        prefixo = f"pergunta {i}"
        opcoes = p.get("opcoes")
        if not isinstance(opcoes, list) or len(opcoes) < 2:
            problemas.append(f"{prefixo}: precisa de pelo menos 2 opcoes")
            continue
        correta = p.get("correta")
        if not isinstance(correta, int) or not (0 <= correta < len(opcoes)):
            problemas.append(
                f"{prefixo}: 'correta' e {correta!r}, mas deveria ser um numero "
                f"entre 0 e {len(opcoes) - 1}"
            )
        if "pergunta" not in p:
            problemas.append(f"{prefixo}: falta o texto da pergunta")

    ids = [p.get("id") for p in fonte["perguntas"]]
    if len(set(ids)) != len(ids):
        problemas.append("ha perguntas com 'id' repetido")

    return problemas


async def sintetizar(texto, voz, rate, destino):
    com = edge_tts.Communicate(text=texto, voice=voz, rate=rate)
    await com.save(str(destino))


async def processar(forcar):
    if not FONTES.exists():
        print(f"A pasta {FONTES} nao existe. Crie-a e coloque os exercicios la.")
        return 0, 0, []

    arquivos = sorted(FONTES.glob("*.json"))
    if not arquivos:
        print(f"Nenhum arquivo .json em {FONTES}.")
        return 0, 0, []

    PASTA.mkdir(parents=True, exist_ok=True)

    gerados, pulados, erros = 0, 0, []

    for arquivo in arquivos:
        nome = arquivo.name
        try:
            fonte = json.loads(arquivo.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            erros.append(f"{nome}: JSON invalido na linha {e.lineno} — {e.msg}")
            continue

        problemas = validar(fonte, arquivo)
        if problemas:
            erros.append(f"{nome}: " + "; ".join(problemas))
            continue

        nivel = fonte["nivel"]
        ident = fonte.get("id") or f"{slug(fonte['titulo'])}-{nivel.lower()}"
        mp3 = PASTA / f"{ident}.mp3"
        saida = PASTA / f"{ident}.json"

        if mp3.exists() and saida.exists() and not forcar:
            pulados += 1
            continue

        voz = VOZES.get(fonte.get("voz", VOZ_PADRAO), fonte.get("voz", VOZES[VOZ_PADRAO]))
        rate = fonte.get("rate") or RATE_POR_NIVEL[nivel]

        print(f"  {ident}  ({nivel}, {voz}, {rate})")
        try:
            await sintetizar(fonte["transcript"], voz, rate, mp3)
        except Exception as e:
            erros.append(f"{nome}: falha ao gerar o audio — {e}")
            continue

        n_palavras = len(fonte["transcript"].split())
        exercicio = {
            "id": ident,
            "titulo": fonte["titulo"],
            "titulo_en": fonte.get("titulo_en", fonte["titulo"]),
            "topico": fonte.get("topico", fonte["titulo"]),
            "nivel": nivel,
            "idioma": fonte.get("idioma", "en"),
            "audio": f"{ident}.mp3",
            "palavras": n_palavras,
            "duracao_estimada": round(n_palavras / WPM_POR_NIVEL[nivel] * 60),
            "voz": voz,
            "transcript": fonte["transcript"],
            "resumo_pt": fonte.get("resumo_pt", ""),
            "glossario": fonte.get("glossario", []),
            "perguntas": fonte["perguntas"],
            "criado_em": datetime.now().isoformat(timespec="seconds"),
        }
        saida.write_text(json.dumps(exercicio, ensure_ascii=False, indent=2), encoding="utf-8")
        gerados += 1

    # Reconstroi o catalogo a partir do que existe de fato na pasta.
    catalogo = []
    for f in sorted(PASTA.glob("*.json")):
        if f.name == "index.json":
            continue
        try:
            ex = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if not (PASTA / ex.get("audio", "")).exists():
            continue
        catalogo.append({
            "id": ex["id"],
            "titulo": ex["titulo"],
            "titulo_en": ex.get("titulo_en", ex["titulo"]),
            "nivel": ex["nivel"],
            "idioma": ex.get("idioma", "en"),
            "topico": ex.get("topico", ""),
            "duracao_estimada": ex.get("duracao_estimada", 0),
            "total_perguntas": len(ex.get("perguntas", [])),
            "criado_em": ex.get("criado_em", ""),
        })

    catalogo.sort(key=lambda e: e.get("criado_em", ""), reverse=True)
    (PASTA / "index.json").write_text(
        json.dumps(catalogo, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    return gerados, pulados, erros


def main():
    p = argparse.ArgumentParser(description="Gera os audios dos exercicios de listening.")
    p.add_argument("--forcar", action="store_true", help="Regera tudo, mesmo o que ja tem audio")
    args = p.parse_args()

    print("Processando exercicios de listening\n")
    gerados, pulados, erros = asyncio.run(processar(args.forcar))

    print(f"\n  gerados: {gerados}   ja existiam: {pulados}   com erro: {len(erros)}")

    if erros:
        print("\nProblemas encontrados:")
        for e in erros:
            print(f"  - {e}")
        # Falha o job so se nada foi gerado — assim um arquivo quebrado
        # nao impede os outros de irem pro ar.
        if gerados == 0:
            sys.exit(1)

    print()


if __name__ == "__main__":
    main()
