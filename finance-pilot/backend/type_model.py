from pathlib import Path

import pandas as pd
from joblib import load


def _candidate_model_paths() -> list[Path]:
    here = Path(__file__).parent
    repo_root = here.parent.parent
    return [
        here / "modelo_tipo_cartao.joblib",
        repo_root / "projects" / "data-transactions" / "nubank" / "models" / "modelo_tipo_cartao.joblib",
    ]


def load_model():
    for path in _candidate_model_paths():
        if path.exists():
            return load(path)
    return None


def predict_types(df: pd.DataFrame, model=None) -> list[str] | None:
    if model is None:
        model = load_model()
    if model is None:
        return None

    X = pd.DataFrame({
        "Texto": df["merchant_clean"].astype(str),
        "Valor": df["amount"].astype(float),
        "DiaSemana": df["day_of_week"].astype(str),
        "Categoria": df.get("category"),
        "Mes": df["month"].astype(int),
    })
    if "Categoria" in X.columns:
        X["Categoria"] = X["Categoria"].fillna("Sem Categoria")
    return model.predict(X).tolist()
