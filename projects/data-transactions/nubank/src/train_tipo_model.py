"""
Treina um modelo Random Forest para classificar Tipo (Casal vs Individual)
com base em Observacoes (title) e Valor.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import json
import sys

import numpy as np
import pandas as pd
from joblib import dump
from sklearn.model_selection import train_test_split, StratifiedKFold, GridSearchCV
from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression, SGDClassifier
from sklearn.svm import LinearSVC
from sklearn.calibration import CalibratedClassifierCV
from sklearn.preprocessing import MinMaxScaler
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    roc_auc_score,
    roc_curve,
    precision_recall_curve,
    average_precision_score,
)

try:
    from skopt import BayesSearchCV
    from skopt.space import Real, Integer, Categorical
except Exception:  # pragma: no cover - optional dependency
    BayesSearchCV = None
    Real = Integer = Categorical = None
from sklearn.utils.validation import check_is_fitted

from functions import normalize_valor_column, clean_transaction_title


def _find_repo_root(start: Path) -> Path:
    current = start.resolve()
    for parent in [current] + list(current.parents):
        if (parent / "finance-pilot").exists():
            return parent
    return start.resolve()


def _resolve_normalize_merchant() -> callable | None:
    repo_root = _find_repo_root(Path(__file__).resolve())
    backend_path = repo_root / "finance-pilot" / "backend"
    if backend_path.exists():
        sys.path.insert(0, str(backend_path))
    try:
        from normalization import normalize_merchant  # type: ignore
        return normalize_merchant
    except Exception:
        return None


def load_and_prepare(
    csv_path: Path,
    window_months: int | None = None,
    card_only: bool = False,
    text_source: str = "observacoes",
    normalize_merchant_fn: callable | None = None,
    use_category: bool = True,
    use_month: bool = True,
    aggregate: bool = False,
    clean_text: bool = True,
) -> tuple[pd.DataFrame, dict]:
    df = pd.read_csv(csv_path)
    meta = {
        "window_months": window_months,
        "card_only": card_only,
        "months_covered": None,
        "use_category": use_category,
        "use_month": use_month,
        "aggregate": aggregate,
    }
    required = {"Observações", "Valor", "Tipo"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Colunas faltando no historico: {sorted(missing)}")

    # Mantem Data se existir para filtragem por janela
    cols = ["Observações", "Valor", "Tipo"]
    if "Data" in df.columns:
        cols.append("Data")
    if use_category:
        if "Categoria" in df.columns:
            cols.append("Categoria")
        elif "Grupo" in df.columns:
            cols.append("Grupo")
    df = df[cols].copy()

    if window_months is not None:
        if "Data" not in df.columns:
            raise ValueError("window_months informado, mas coluna 'Data' nao existe no historico.")
        df["Data_dt"] = pd.to_datetime(df["Data"], errors="coerce", dayfirst=True)
        max_dt = df["Data_dt"].max()
        if pd.isna(max_dt):
            raise ValueError("Nao foi possivel interpretar a coluna 'Data' para filtrar janela.")
        cutoff = max_dt - pd.DateOffset(months=window_months)
        df = df[df["Data_dt"] >= cutoff].copy()

    # cria variavel de dia da semana
    if "Data" in df.columns:
        df["Data_dt"] = pd.to_datetime(df["Data"], errors="coerce", dayfirst=True)
        if card_only:
            df = df[df["Data"].astype(str).str.contains(r"00:00:00")].copy()
        df["DiaSemana"] = df["Data_dt"].dt.day_name(locale="pt_BR").fillna("desconhecido")
        if use_month:
            df["Mes"] = df["Data_dt"].dt.month.fillna(0).astype(int)
    else:
        df["DiaSemana"] = "desconhecido"
        if use_month:
            df["Mes"] = 0

    # limpa observacoes e valor
    raw_obs = df["Observações"].astype(str).str.strip()
    if text_source == "merchant_clean":
        if normalize_merchant_fn is None:
            normalize_merchant_fn = _resolve_normalize_merchant()
        if normalize_merchant_fn is None:
            raise ValueError("Nao foi possivel carregar normalize_merchant para usar merchant_clean.")
        df["Texto"] = raw_obs.apply(normalize_merchant_fn)
    else:
        if clean_text:
            df["Texto"] = raw_obs.apply(clean_transaction_title)
        else:
            df["Texto"] = raw_obs

    df = normalize_valor_column(df, "Valor")

    df["Tipo"] = df["Tipo"].astype(str).str.strip().str.title()
    if use_category:
        if "Categoria" not in df.columns and "Grupo" in df.columns:
            df["Categoria"] = df["Grupo"]
        if "Categoria" in df.columns:
            df["Categoria"] = df["Categoria"].astype(str).str.strip().str.title()
            df["Categoria"] = df["Categoria"].replace({"Nan": ""}).fillna("")

    # remove linhas invalidas
    df = df.dropna(subset=["Texto", "Valor", "Tipo"])
    df = df[df["Texto"].str.len() > 0]

    # filtra apenas classes alvo
    df = df[df["Tipo"].isin(["Casal", "Individual"])]

    if aggregate:
        group_cols = ["Texto", "Tipo", "DiaSemana"]
        if use_category and "Categoria" in df.columns:
            group_cols.append("Categoria")
        if use_month and "Mes" in df.columns:
            group_cols.append("Mes")
        df = (
            df.groupby(group_cols, as_index=False, dropna=False)
            .agg({"Valor": "sum"})
        )

    if "Data_dt" in df.columns:
        min_dt = df["Data_dt"].min()
        max_dt = df["Data_dt"].max()
        if pd.notna(min_dt) and pd.notna(max_dt):
            meta["months_covered"] = (max_dt.year - min_dt.year) * 12 + (max_dt.month - min_dt.month) + 1

    return df, meta


class DenseTransformer:
    """Converte matriz esparsa para densa quando necessario."""

    def fit(self, X, y=None):
        return self

    def transform(self, X):
        if hasattr(X, "toarray"):
            return X.toarray()
        return X


def build_preprocessor(
    use_minmax_for_value: bool = False,
    text_col: str = "Texto",
    category_col: str | None = None,
    month_col: str | None = None,
) -> ColumnTransformer:
    value_scaler = MinMaxScaler() if use_minmax_for_value else StandardScaler(with_mean=False)

    transformers = [
        (
            "texto",
            TfidfVectorizer(
                lowercase=True,
                ngram_range=(1, 2),
                min_df=2,
                max_features=20000,
            ),
            text_col,
        ),
        (
            "valor",
            Pipeline([
                ("scale", value_scaler),
            ]),
            ["Valor"],
        ),
        (
            "dia_semana",
            Pipeline([
                ("tfidf", TfidfVectorizer(lowercase=True)),
            ]),
            "DiaSemana",
        ),
    ]

    if category_col:
        transformers.append((
            "categoria",
            OneHotEncoder(handle_unknown="ignore"),
            [category_col],
        ))

    if month_col:
        transformers.append((
            "mes",
            OneHotEncoder(handle_unknown="ignore"),
            [month_col],
        ))

    return ColumnTransformer(transformers=transformers, remainder="drop")

def build_model_spaces(
    random_state: int,
    text_col: str = "Texto",
    category_col: str | None = None,
    month_col: str | None = None,
):
    # Modelos que lidam bem com dados esparsos
    models = []

    # Logistic Regression
    lr = LogisticRegression(
        max_iter=2000,
        solver="saga",
        class_weight="balanced",
        random_state=random_state,
    )
    models.append({
        "name": "LogisticRegression",
        "pipeline": Pipeline([
            ("prep", build_preprocessor(text_col=text_col, category_col=category_col, month_col=month_col)),
            ("clf", lr),
        ]),
        "search_space": {
            "clf__C": Real(1e-3, 1e2, prior="log-uniform") if Real else None,
            "clf__penalty": Categorical(["l2"]) if Categorical else None,
        },
        "param_grid": {
            "clf__C": [0.01, 0.1, 1.0, 10.0],
            "clf__penalty": ["l2"],
        },
    })

    # Linear SVM com calibracao para probas
    lsvc = LinearSVC(
        class_weight="balanced",
        random_state=random_state,
    )
    models.append({
        "name": "LinearSVC_Calibrated",
        "pipeline": Pipeline([
            ("prep", build_preprocessor(text_col=text_col, category_col=category_col, month_col=month_col)),
            ("clf", CalibratedClassifierCV(lsvc, method="sigmoid", cv=3)),
        ]),
        "search_space": {
            "clf__estimator__C": Real(1e-3, 1e2, prior="log-uniform") if Real else None,
        },
        "param_grid": {
            "clf__estimator__C": [0.01, 0.1, 1.0, 10.0],
        },
    })

    # SGD (logistic regression online)
    sgd = SGDClassifier(
        loss="log_loss",
        penalty="l2",
        class_weight="balanced",
        random_state=random_state,
        max_iter=2000,
        tol=1e-4,
    )
    models.append({
        "name": "SGDClassifier",
        "pipeline": Pipeline([
            ("prep", build_preprocessor(text_col=text_col, category_col=category_col, month_col=month_col)),
            ("clf", sgd),
        ]),
        "search_space": {
            "clf__alpha": Real(1e-6, 1e-2, prior="log-uniform") if Real else None,
            "clf__l1_ratio": Real(0.0, 1.0) if Real else None,
            "clf__penalty": Categorical(["l2", "elasticnet"]) if Categorical else None,
        },
        "param_grid": {
            "clf__alpha": [1e-4, 1e-3, 1e-2],
            "clf__penalty": ["l2", "elasticnet"],
            "clf__l1_ratio": [0.15, 0.5, 0.85],
        },
    })

    # Random Forest (necessita densificar)
    rf = RandomForestClassifier(
        random_state=random_state,
        n_jobs=1,
        class_weight="balanced",
    )
    models.append({
        "name": "RandomForest",
        "pipeline": Pipeline([
            ("prep", build_preprocessor(text_col=text_col)),
            ("to_dense", DenseTransformer()),
            ("clf", rf),
        ]),
        "search_space": {
            "clf__n_estimators": Integer(200, 600) if Integer else None,
            "clf__max_depth": Integer(5, 40) if Integer else None,
            "clf__min_samples_split": Integer(2, 10) if Integer else None,
            "clf__min_samples_leaf": Integer(1, 5) if Integer else None,
        },
        "param_grid": {
            "clf__n_estimators": [200, 400, 600],
            "clf__max_depth": [10, 20, None],
            "clf__min_samples_split": [2, 5],
            "clf__min_samples_leaf": [1, 2],
        },
    })

    return models


def evaluate(model, X_test, y_test) -> dict:
    y_pred = model.predict(X_test)
    report = classification_report(y_test, y_pred, output_dict=True, zero_division=0)
    cm = confusion_matrix(y_test, y_pred, labels=["Casal", "Individual"])

    metrics = {
        "accuracy": accuracy_score(y_test, y_pred),
        "precision_macro": precision_score(y_test, y_pred, average="macro", zero_division=0),
        "recall_macro": recall_score(y_test, y_pred, average="macro", zero_division=0),
        "f1_macro": f1_score(y_test, y_pred, average="macro", zero_division=0),
    }

    # roc-auc se disponivel
    roc_auc = None
    ap = None
    roc_curve_data = None
    pr_curve_data = None
    scores = None
    if hasattr(model, "predict_proba"):
        try:
            proba = model.predict_proba(X_test)
            classes = list(model.classes_)
            if "Casal" in classes and "Individual" in classes:
                idx = classes.index("Individual")
                scores = proba[:, idx]
        except Exception:
            scores = None
    elif hasattr(model, "decision_function"):
        try:
            scores = model.decision_function(X_test)
        except Exception:
            scores = None

    if scores is not None:
        y_true = (y_test == "Individual").astype(int)
        roc_auc = roc_auc_score(y_true, scores)
        fpr, tpr, _ = roc_curve(y_true, scores)
        prec, rec, _ = precision_recall_curve(y_true, scores)
        ap = average_precision_score(y_true, scores)
        roc_curve_data = {"fpr": fpr.tolist(), "tpr": tpr.tolist()}
        pr_curve_data = {"precision": prec.tolist(), "recall": rec.tolist()}

    # monetary confusion (sum of Valor for misclassifications)
    valor = X_test["Valor"].astype(float)
    casal_to_individual = valor[(y_test == "Casal") & (y_pred == "Individual")].sum()
    individual_to_casal = valor[(y_test == "Individual") & (y_pred == "Casal")].sum()

    return {
        "report": report,
        "confusion_matrix": cm.tolist(),
        "metrics": metrics,
        "roc_auc": roc_auc,
        "average_precision": ap,
        "roc_curve": roc_curve_data,
        "pr_curve": pr_curve_data,
        "monetary_confusion": {
            "casal_to_individual": float(casal_to_individual),
            "individual_to_casal": float(individual_to_casal),
        },
        "y_pred": y_pred,
    }


def _svg_bar_chart(data, title, height=180, width=640):
    # data: list of (label, value) with value in [0,1] or positive
    max_val = max([v for _, v in data] + [1e-9])
    bar_width = max(20, int((width - 120) / max(len(data), 1)))
    chart_height = height - 40
    svg_parts = [
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
        f'xmlns="http://www.w3.org/2000/svg" role="img" aria-label="{title}">'
    ]
    svg_parts.append(f'<rect x="0" y="0" width="{width}" height="{height}" fill="#ffffff"/>')
    svg_parts.append(f'<text x="10" y="20" font-size="14" font-family="Arial">{title}</text>')
    x = 60
    for label, value in data:
        bar_h = int((value / max_val) * chart_height)
        y = 30 + (chart_height - bar_h)
        svg_parts.append(f'<rect x="{x}" y="{y}" width="{bar_width}" height="{bar_h}" fill="#4C78A8"/>')
        svg_parts.append(f'<text x="{x}" y="{height-6}" font-size="10" font-family="Arial" '
                         f'text-anchor="start" transform="rotate(0 {x},{height-6})">{label}</text>')
        svg_parts.append(f'<text x="{x}" y="{y-4}" font-size="10" font-family="Arial">{value:.2f}</text>')
        x += bar_width + 10
    svg_parts.append('</svg>')
    return ''.join(svg_parts)


def _svg_confusion_matrix(cm, labels, title, cell_size=60):
    # cm: 2x2 list
    width = cell_size * 2 + 140
    height = cell_size * 2 + 80
    max_val = max([v for row in cm for v in row] + [1])
    svg = [
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
        f'xmlns="http://www.w3.org/2000/svg" role="img" aria-label="{title}">'
    ]
    svg.append(f'<text x="10" y="20" font-size="14" font-family="Arial">{title}</text>')
    x0, y0 = 100, 40
    # axis labels
    svg.append(f'<text x="{x0}" y="{y0-8}" font-size="10" font-family="Arial">Pred</text>')
    svg.append(f'<text x="{x0-30}" y="{y0+cell_size}" font-size="10" font-family="Arial" '
               f'transform="rotate(-90 {x0-30},{y0+cell_size})">Real</text>')
    for j, lab in enumerate(labels):
        svg.append(f'<text x="{x0 + j*cell_size + 10}" y="{y0-8}" font-size="10" font-family="Arial">{lab}</text>')
    for i, lab in enumerate(labels):
        svg.append(f'<text x="{x0-70}" y="{y0 + i*cell_size + 35}" font-size="10" font-family="Arial">{lab}</text>')
    # cells
    for i in range(2):
        for j in range(2):
            val = cm[i][j]
            intensity = int(255 - (val / max_val) * 180)
            color = f'rgb(76,120,{intensity})'
            x = x0 + j * cell_size
            y = y0 + i * cell_size
            svg.append(f'<rect x="{x}" y="{y}" width="{cell_size}" height="{cell_size}" fill="{color}" />')
            svg.append(f'<text x="{x + cell_size/2}" y="{y + cell_size/2 + 4}" '
                       f'font-size="12" font-family="Arial" text-anchor="middle">{val}</text>')
    svg.append('</svg>')
    return ''.join(svg)


def _svg_line_chart(x, y, title, x_label, y_label, width=360, height=240):
    if not x or not y:
        return ""
    padding = 40
    plot_w = width - 2 * padding
    plot_h = height - 2 * padding
    x_min, x_max = min(x), max(x)
    y_min, y_max = min(y), max(y)
    x_range = max(x_max - x_min, 1e-9)
    y_range = max(y_max - y_min, 1e-9)

    points = []
    for xi, yi in zip(x, y):
        px = padding + (xi - x_min) / x_range * plot_w
        py = padding + plot_h - (yi - y_min) / y_range * plot_h
        points.append(f"{px:.2f},{py:.2f}")

    svg = [
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
        f'xmlns="http://www.w3.org/2000/svg" role="img" aria-label="{title}">'
    ]
    svg.append(f'<rect x="0" y="0" width="{width}" height="{height}" fill="#ffffff"/>')
    svg.append(f'<text x="10" y="18" font-size="12" font-family="Arial">{title}</text>')
    svg.append(f'<polyline fill="none" stroke="#F58518" stroke-width="2" points="{" ".join(points)}"/>')
    svg.append(f'<text x="{padding}" y="{height-6}" font-size="10" font-family="Arial">{x_label}</text>')
    svg.append(f'<text x="4" y="{padding}" font-size="10" font-family="Arial" transform="rotate(-90 4,{padding})">{y_label}</text>')
    svg.append('</svg>')
    return ''.join(svg)


def render_html(output_path: Path, metrics: dict, report: dict, cm: list, params: dict):
    cm_df = pd.DataFrame(
        cm,
        index=["Casal", "Individual"],
        columns=["Pred Casal", "Pred Individual"],
    )

    report_df = pd.DataFrame(report).transpose()

    metrics_df = pd.DataFrame([{
        **metrics,
        "roc_auc": params.get("roc_auc"),
        "avg_precision": params.get("average_precision"),
    }])

    metric_bars = _svg_bar_chart(
        [
            ("acc", metrics["accuracy"]),
            ("prec", metrics["precision_macro"]),
            ("rec", metrics["recall_macro"]),
            ("f1", metrics["f1_macro"]),
        ],
        "Metricas (0-1)",
    )
    cm_svg = _svg_confusion_matrix(cm, ["Casal", "Individual"], "Confusion Matrix")
    roc_svg = ""
    pr_svg = ""
    if params.get("roc_curve"):
        roc_svg = _svg_line_chart(
            params["roc_curve"]["fpr"],
            params["roc_curve"]["tpr"],
            "ROC Curve",
            "FPR",
            "TPR",
        )
    if params.get("pr_curve"):
        pr_svg = _svg_line_chart(
            params["pr_curve"]["recall"],
            params["pr_curve"]["precision"],
            "Precision-Recall",
            "Recall",
            "Precision",
        )

    model_summaries_df = pd.DataFrame(params.get("model_summaries", []))
    monetary = params.get("monetary_confusion", {})
    monetary_df = pd.DataFrame([{
        "Casal -> Individual (R$)": monetary.get("casal_to_individual", 0.0),
        "Individual -> Casal (R$)": monetary.get("individual_to_casal", 0.0),
    }])
    html = f"""
<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <title>Relatorio Modelo Tipo</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; }}
    table {{ border-collapse: collapse; width: 100%; margin-bottom: 24px; }}
    th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
    th {{ background: #f3f3f3; }}
    h1, h2 {{ margin-top: 24px; }}
    .note {{ color: #666; font-size: 0.9em; }}
    code {{ background: #f7f7f7; padding: 2px 4px; }}
    .charts {{ display: flex; flex-wrap: wrap; gap: 24px; align-items: flex-start; }}
  </style>
</head>
<body>
  <h1>Relatorio de Avaliacao - {params.get("model", "Modelo")}</h1>
  <p class="note">Base historica: Observacoes + Valor para estimar Tipo (Casal vs Individual).</p>

  <h2>Metricas Principais</h2>
  <div class="charts">
    {metric_bars}
    {cm_svg}
    {roc_svg}
    {pr_svg}
  </div>
  {metrics_df.to_html(index=False)}

  <h2>Classification Report</h2>
  {report_df.to_html()}

  <h2>Confusao Financeira (Valor)</h2>
  {monetary_df.to_html(index=False)}

  <h2>Comparacao de Modelos (CV)</h2>
  {model_summaries_df.to_html(index=False) if not model_summaries_df.empty else "<p>Sem dados.</p>"}

  <h2>Confusion Matrix</h2>
  {cm_df.to_html()}

  <h2>Melhores Parametros</h2>
  <pre>{json.dumps(params.get("best_params", {}), indent=2, ensure_ascii=False)}</pre>
</body>
</html>
"""

    output_path.write_text(html, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Treina modelo para classificar Tipo usando historico.")
    parser.add_argument(
        "--input",
        default="__AUTO__",
        help="Caminho do CSV historico",
    )
    parser.add_argument(
        "--output",
        default="reports/relatorio_modelo_tipo.html",
        help="Caminho do HTML de saida",
    )
    parser.add_argument("--test-size", type=float, default=0.2)
    parser.add_argument("--val-size", type=float, default=0.1)
    parser.add_argument("--random-state", type=int, default=42)
    parser.add_argument("--n-iter", type=int, default=25)
    parser.add_argument("--cv", type=int, default=5)
    parser.add_argument("--window-months", type=int, default=None, help="Filtra historico pelos ultimos N meses")
    parser.add_argument("--card-only", action="store_true", help="Usa apenas transacoes do cartao (hora 00:00:00)")
    parser.add_argument("--json-output", default=None, help="Salva resumo em JSON")
    parser.add_argument("--model-output", default=None, help="Salva o modelo treinado (.joblib)")
    parser.add_argument("--errors-csv", default=None, help="Salva CSV com linhas preditas incorretamente")
    parser.add_argument("--aggregate", action="store_true", help="Agrupa por descricao/categoria e soma valor")
    parser.add_argument("--no-category", action="store_true", help="Nao usa coluna de categoria")
    parser.add_argument("--no-month", action="store_true", help="Nao usa coluna de mes")
    parser.add_argument(
        "--text-source",
        choices=["observacoes", "merchant_clean"],
        default="observacoes",
        help="Fonte do texto para o modelo",
    )
    parser.add_argument(
        "--no-clean-text",
        action="store_true",
        help="Nao aplica limpeza nas descricoes (usa texto bruto).",
    )

    args = parser.parse_args()

    def find_repo_root(start: Path) -> Path:
        current = start.resolve()
        for parent in [current] + list(current.parents):
            if (parent / "finance-pilot").exists():
                return parent
        return start.resolve()

    repo_root = find_repo_root(Path.cwd())
    if args.input == "__AUTO__":
        input_path = repo_root / "finance-pilot" / "data" / "findata_backup_20260202_164435.csv"
    else:
        input_path = Path(args.input)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    use_category = not args.no_category
    use_month = not args.no_month

    df, meta = load_and_prepare(
        input_path,
        window_months=args.window_months,
        card_only=args.card_only,
        text_source=args.text_source,
        use_category=use_category,
        use_month=use_month,
        aggregate=args.aggregate,
        clean_text=not args.no_clean_text,
    )

    # split: train/val/test
    feature_cols = ["Texto", "Valor", "DiaSemana"]
    if use_category and "Categoria" in df.columns:
        feature_cols.append("Categoria")
    if use_month and "Mes" in df.columns:
        feature_cols.append("Mes")
    if "Data" in df.columns:
        feature_cols.append("Data")
    X = df[feature_cols].copy()
    if use_category and "Categoria" in X.columns:
        X["Categoria"] = X["Categoria"].replace({"": "Sem Categoria"}).fillna("Sem Categoria")
    y = df["Tipo"]

    X_trainval, X_test, y_trainval, y_test = train_test_split(
        X,
        y,
        test_size=args.test_size,
        random_state=args.random_state,
        stratify=y,
    )

    # opcional, mantemos val separado para futuro
    if args.val_size > 0:
        val_ratio = args.val_size / (1 - args.test_size)
        X_train, X_val, y_train, y_val = train_test_split(
            X_trainval,
            y_trainval,
            test_size=val_ratio,
            random_state=args.random_state,
            stratify=y_trainval,
        )
    else:
        X_train, y_train = X_trainval, y_trainval
        X_val, y_val = None, None

    cv = StratifiedKFold(n_splits=args.cv, shuffle=True, random_state=args.random_state)

    model_spaces = build_model_spaces(
        args.random_state,
        text_col="Texto",
        category_col="Categoria" if use_category and "Categoria" in df.columns else None,
        month_col="Mes" if use_month and "Mes" in df.columns else None,
    )
    best_result = None
    model_summaries = []

    use_bayes = BayesSearchCV is not None

    for entry in model_spaces:
        if use_bayes and entry["search_space"] and entry["search_space"].get(list(entry["search_space"].keys())[0]) is not None:
            search = BayesSearchCV(
                entry["pipeline"],
                search_spaces=entry["search_space"],
                n_iter=args.n_iter,
                scoring="f1_macro",
                cv=cv,
                n_jobs=1,
                verbose=0,
                random_state=args.random_state,
            )
        else:
            search = GridSearchCV(
                entry["pipeline"],
                param_grid=entry["param_grid"],
                scoring="f1_macro",
                cv=cv,
                n_jobs=1,
                verbose=0,
            )

        search.fit(X_train, y_train)

        model_summaries.append({
            "model": entry["name"],
            "best_score": search.best_score_,
            "best_params": search.best_params_,
        })

        if best_result is None or search.best_score_ > best_result["best_score"]:
            best_result = {
                "model": entry["name"],
                "best_score": search.best_score_,
                "search": search,
            }

    best_model = best_result["search"].best_estimator_
    check_is_fitted(best_model)

    eval_data = evaluate(best_model, X_test, y_test)

    params = {
        "best_params": best_result["search"].best_params_,
        "roc_auc": eval_data.get("roc_auc"),
        "average_precision": eval_data.get("average_precision"),
        "roc_curve": eval_data.get("roc_curve"),
        "pr_curve": eval_data.get("pr_curve"),
        "monetary_confusion": eval_data.get("monetary_confusion"),
        "sizes": {
            "train": len(X_train),
            "val": 0 if X_val is None else len(X_val),
            "test": len(X_test),
        },
        "model": best_result["model"],
        "model_summaries": model_summaries,
        "meta": meta,
    }

    render_html(
        output_path,
        eval_data["metrics"],
        eval_data["report"],
        eval_data["confusion_matrix"],
        params,
    )

    if args.model_output:
        model_path = Path(args.model_output)
        model_path.parent.mkdir(parents=True, exist_ok=True)
        dump(best_model, model_path)

    if args.errors_csv:
        errors_path = Path(args.errors_csv)
        errors_path.parent.mkdir(parents=True, exist_ok=True)
        y_pred = eval_data.get("y_pred")
        errors_mask = y_pred != y_test.values
        errors_df = X_test.copy()
        errors_df["tipo_real"] = y_test.values
        errors_df["tipo_predito"] = y_pred
        if "Data" in errors_df.columns:
            errors_df["Data"] = errors_df["Data"].astype(str)
        errors_df = errors_df[errors_mask]
        errors_df.to_csv(errors_path, index=False)

    if args.json_output:
        json_path = Path(args.json_output)
        json_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "metrics": eval_data["metrics"],
            "report": eval_data["report"],
            "confusion_matrix": eval_data["confusion_matrix"],
            "monetary_confusion": eval_data.get("monetary_confusion"),
            "roc_auc": eval_data.get("roc_auc"),
            "average_precision": eval_data.get("average_precision"),
            "best_params": best_result["search"].best_params_,
            "model": best_result["model"],
            "model_summaries": model_summaries,
            "meta": meta,
        }
        json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Relatorio salvo em: {output_path}")


if __name__ == "__main__":
    main()
