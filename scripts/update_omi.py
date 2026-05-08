"""
Script per aggiornare il dataset OMI completo dall'open data di Ondata.
Scarica il file valori.7z dal repository GitHub, lo decomprime e converte
nel formato usato dall'applicazione (app/data/omi_full.csv).

Uso:
    python scripts/update_omi.py
"""
from __future__ import annotations

import re
import shutil
import tempfile
from pathlib import Path

import httpx
import pandas as pd


def download_omi_archive(url: str, dest: Path) -> None:
    print(f"Scarico {url} ...")
    with httpx.Client(timeout=120, follow_redirects=True) as client:
        r = client.get(url)
        r.raise_for_status()
    dest.write_bytes(r.content)
    print(f"Salvato {dest} ({len(r.content):,} bytes)")


def extract_7z(archive: Path, out_dir: Path) -> None:
    print(f"Decomprimo {archive} ...")
    try:
        import py7zr
    except ImportError as exc:
        raise RuntimeError("py7zr non installato. Esegui: pip install py7zr") from exc
    with py7zr.SevenZipFile(archive, mode="r") as z:
        z.extractall(path=out_dir)
    print("Decompressione completata")


def extract_semestre(filename: str) -> str:
    m = re.search(r"(\d{4})(\d)(?=_VALORI)", str(filename))
    if m:
        anno, sem = m.groups()
        sem_rom = "I" if sem == "1" else "II"
        return f"{anno}-{sem_rom}"
    return ""


def convert_omi_csv(source_csv: Path, dest_csv: Path) -> None:
    print(f"Leggo {source_csv} ...")
    df = pd.read_csv(source_csv, low_memory=False)
    print(f"Righe totali: {len(df):,}")

    tipologie_residenziali = [
        "Abitazioni civili",
        "Abitazioni signorili",
        "Abitazioni di tipo economico",
        "Ville e Villini",
    ]
    df = df[df["Descr_Tipologia"].isin(tipologie_residenziali)].copy()
    print(f"Righe residenziali: {len(df):,}")

    df["semestre"] = df["file"].apply(extract_semestre)
    df["stato_conservativo"] = df["Stato"].str.strip().str.title()

    # Prendi solo l'ultimo semestre per ogni combinazione
    df = df.sort_values("file", ascending=False)
    df = df.drop_duplicates(
        subset=["Comune_descrizione", "Zona", "Descr_Tipologia", "Stato"],
        keep="first",
    )
    print(f"Righe uniche (ultimo semestre): {len(df):,}")

    out = df.rename(
        columns={
            "Comune_descrizione": "citta",
            "Zona": "zona",
            "Descr_Tipologia": "tipologia",
            "Compr_min": "prezzo_min_mq",
            "Compr_max": "prezzo_max_mq",
        }
    )[["citta", "zona", "tipologia", "stato_conservativo", "prezzo_min_mq", "prezzo_max_mq", "semestre"]]

    out.to_csv(dest_csv, index=False)
    print(f"Dataset OMI aggiornato salvato in {dest_csv} ({len(out):,} righe, {out['citta'].nunique():,} città)")


def main() -> None:
    repo_url = "https://raw.githubusercontent.com/ondata/quotazioni-immobiliari-agenzia-entrate/master/data/valori.7z"
    project_root = Path(__file__).resolve().parent.parent
    data_dir = project_root / "app" / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        archive = tmp_path / "valori.7z"
        download_omi_archive(repo_url, archive)
        extract_7z(archive, tmp_path)
        source_csv = tmp_path / "valori.csv"
        if not source_csv.exists():
            raise FileNotFoundError(f"{source_csv} non trovato dopo decompressione")
        convert_omi_csv(source_csv, data_dir / "omi_full.csv")


if __name__ == "__main__":
    main()
