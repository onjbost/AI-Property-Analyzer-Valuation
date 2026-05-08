"""
Endpoint amministrativi per la gestione del sistema.
"""
from __future__ import annotations

import re
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Optional

import pandas as pd
from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from app.core.config import get_settings
from app.core.logging import logger
from app.services.omi_calculator import _load_omi_dataframe

settings = get_settings()
router = APIRouter()


def _extract_semestre_from_filename(filename: str) -> str:
    m = re.search(r"(\d{4})(\d)(?=_VALORI)", str(filename))
    if m:
        anno, sem = m.groups()
        sem_rom = "I" if sem == "1" else "II"
        return f"{anno}-{sem_rom}"
    return ""


def _convert_omi_csv(source_csv: Path, dest_csv: Path, semestre_override: Optional[str] = None) -> dict:
    df = pd.read_csv(source_csv, sep=";", low_memory=False)
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

    if semestre_override:
        df["semestre"] = semestre_override
    else:
        df["semestre"] = df["file"].apply(_extract_semestre_from_filename)

    df["stato_conservativo"] = df["Stato"].str.strip().str.title()
    df = df.sort_values("file", ascending=False)
    df = df.drop_duplicates(
        subset=["Comune_descrizione", "Zona", "Descr_Tipologia", "Stato"],
        keep="first",
    )

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
    return {"rows": len(out), "cities": int(out["citta"].nunique())}


@router.post(
    "/admin/update-omi",
    status_code=status.HTTP_200_OK,
    summary="Aggiorna il dataset OMI da ZIP ufficiale",
    tags=["Amministrazione"],
)
async def update_omi_dataset(
    file: UploadFile = File(..., description="File ZIP dell'Agenzia delle Entrate contenente QI_*_VALORI.csv"),
    semestre: Optional[str] = Form(None, description="Semestre di riferimento (es. 2025-II). Se omesso, estratto dal nome file."),
):
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Il file deve essere un archivio ZIP.")

    data_dir = Path(settings.omi_csv_path).parent
    data_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        zip_path = tmp_path / "omi_upload.zip"
        with zip_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        with zipfile.ZipFile(zip_path, "r") as z:
            valori_files = [n for n in z.namelist() if n.endswith("_VALORI.csv")]
            if not valori_files:
                raise HTTPException(status_code=400, detail="Nessun file *_VALORI.csv trovato nello ZIP.")
            valori_name = valori_files[0]
            z.extract(valori_name, tmp_path)

        source_csv = tmp_path / valori_name
        dest_csv = Path(settings.omi_csv_path)

        result = _convert_omi_csv(source_csv, dest_csv, semestre_override=semestre)

    # Invalida cache dataset OMI
    _load_omi_dataframe.cache_clear()

    logger.info(
        "Dataset OMI aggiornato da %s | righe=%s | città=%s | semestre=%s",
        file.filename,
        result["rows"],
        result["cities"],
        semestre or "auto",
    )
    return {
        "message": "Dataset OMI aggiornato con successo.",
        "file": file.filename,
        "semestre": semestre or "auto",
        "rows": result["rows"],
        "cities": result["cities"],
    }
