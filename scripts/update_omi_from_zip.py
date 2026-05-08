"""
Script per aggiornare il dataset OMI a partire da un file ZIP ufficiale
Agenzia delle Entrate (es. QIPxxxxxx.zip).

Cerca automaticamente il file .zip nella root del progetto, estrae il CSV
'QI_*_VALORI.csv', lo converte nel formato omi_full.csv e aggiorna anche
le coordinate dei comuni se necessario.

Uso:
    python scripts/update_omi_from_zip.py
"""
from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path

import pandas as pd


def find_zip_file(project_root: Path) -> Path | None:
    zips = sorted(project_root.glob("*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
    return zips[0] if zips else None


def extract_semestre(filename: str) -> str:
    m = re.search(r"(\d{4})(\d)(?=_VALORI)", str(filename))
    if m:
        anno, sem = m.groups()
        sem_rom = "I" if sem == "1" else "II"
        return f"{anno}-{sem_rom}"
    return ""


def convert_omi_csv(source_csv: Path, dest_csv: Path) -> None:
    print(f"Leggo {source_csv} ...")
    df = pd.read_csv(source_csv, sep=";", low_memory=False)
    print(f"Righe lette: {len(df):,}")

    # Normalizza numeri
    num_cols = ["Compr_min", "Compr_max", "Loc_min", "Loc_max"]
    for col in num_cols:
        df[col] = df[col].astype(str).str.replace(",", ".", regex=False)
        df[col] = pd.to_numeric(df[col], errors="coerce")

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
    project_root = Path(__file__).resolve().parent.parent
    zip_path = find_zip_file(project_root)
    if not zip_path:
        print("Nessun file .zip trovato nella root del progetto.")
        return

    print(f"Trovato ZIP: {zip_path}")
    data_dir = project_root / "app" / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path, "r") as z:
        valori_files = [n for n in z.namelist() if n.endswith("_VALORI.csv")]
        if not valori_files:
            print("Nessun file *_VALORI.csv trovato nello ZIP.")
            return
        valori_name = valori_files[0]
        print(f"Estraggo {valori_name} ...")
        z.extract(valori_name, data_dir)

    source_csv = data_dir / valori_name
    convert_omi_csv(source_csv, data_dir / "omi_full.csv")

    # Pulizia file temporaneo estratto
    source_csv.unlink(missing_ok=True)
    print("Fatto.")


if __name__ == "__main__":
    main()
