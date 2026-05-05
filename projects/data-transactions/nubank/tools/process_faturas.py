#!/usr/bin/env python3
"""
Processa faturas do Nubank (Victor e Larissa), padroniza descricoes,
aplica categorias, estima tipo (apenas Victor) e gera outputs + HTML.
"""
import argparse
import sys
from pathlib import Path

import pandas as pd


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _load_backend():
    repo_root = _repo_root()
    backend_dir = repo_root / "finance-pilot" / "backend"
    sys.path.insert(0, str(backend_dir))
    from normalization import normalize_merchant  # type: ignore
    from category_mapping import load_category_map, get_category  # type: ignore
    from type_model import load_model, predict_types  # type: ignore

    return normalize_merchant, load_category_map, get_category, load_model, predict_types


def _day_name_pt(date_value) -> str:
    try:
        return pd.to_datetime(date_value).day_name(locale="pt_BR")
    except Exception:
        weekday = pd.to_datetime(date_value).weekday()
        names = [
            "Segunda feira",
            "Terça feira",
            "Quarta feira",
            "Quinta feira",
            "Sexta feira",
            "Sábado",
            "Domingo",
        ]
        return names[weekday]


def _process_file(path: Path, owner: str, normalize_merchant, category_map, get_category):
    df = pd.read_csv(path)
    df = df.rename(columns={"title": "merchant_raw"})

    # Remove pagamentos recebidos e valores negativos antes de qualquer coisa
    df = df[~df["merchant_raw"].astype(str).str.contains("Pagamento recebido", na=False)].copy()
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
    df = df[df["amount"] >= 0].copy()

    # Mantem descricao original para o modelo/saida
    df["merchant_clean"] = df["merchant_raw"].astype(str).str.strip()
    # Normaliza apenas para categorizar
    df["merchant_norm"] = df["merchant_raw"].astype(str).apply(normalize_merchant)
    df["category"] = df["merchant_norm"].apply(lambda x: get_category(x, category_map))

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["day_of_week"] = df["date"].apply(_day_name_pt)
    df["month"] = df["date"].dt.month
    df["owner"] = owner

    return df


def _assign_type(df_agg: pd.DataFrame, owner: str, predict_types, model):
    if owner.strip().lower() == "larissa":
        df_agg["type"] = "Individual"
        return df_agg

    preds = predict_types(df_agg, model=model)
    if preds is None:
        df_agg["type"] = None
    else:
        df_agg["type"] = preds
    return df_agg


def _final_group(df: pd.DataFrame) -> pd.DataFrame:
    final_cols = ["merchant_clean", "category", "owner", "type"]
    return (
        df.groupby(final_cols, as_index=False, dropna=False)
        .agg({"amount": "sum"})
        .sort_values(["owner", "amount"], ascending=[True, False])
    )


def _render_html(path: Path, victor_df: pd.DataFrame, larissa_df: pd.DataFrame, consolidated_df: pd.DataFrame, victor_file: str, larissa_file: str):
    def _summary_by_category(df: pd.DataFrame):
        tmp = df.copy()
        tmp["category"] = tmp["category"].fillna("Sem Categoria")
        return tmp.groupby("category", as_index=False).agg({"amount": "sum"}).sort_values("amount", ascending=False)

    def _summary_by_type(df: pd.DataFrame):
        tmp = df.copy()
        tmp["type"] = tmp["type"].fillna("Sem Tipo")
        return tmp.groupby("type", as_index=False).agg({"amount": "sum"}).sort_values("amount", ascending=False)

    # Build HTML
    sections = []

    def _table(title: str, df: pd.DataFrame) -> str:
        return f"<h2>{title}</h2>\n" + df.to_html(index=False, border=0)

    sections.append(_table("Victor - Resumo por Categoria", _summary_by_category(victor_df)))
    sections.append(_table("Victor - Resumo por Tipo", _summary_by_type(victor_df)))
    sections.append(_table("Victor - Lista Final (Agrupada)", victor_df))

    sections.append(_table("Larissa - Resumo por Categoria", _summary_by_category(larissa_df)))
    sections.append(_table("Larissa - Lista Final (Agrupada)", larissa_df))

    sections.append(_table("Consolidado - Lista Final (Agrupada)", consolidated_df))

    html = f"""
<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<title>Preview Faturas (Agrupado Final)</title>
<style>
:root {{
  --bg: #f7f4ef;
  --ink: #1c1b1a;
  --muted: #6c6a67;
  --accent: #a9732a;
  --border: #e3ded6;
  --panel: #ffffff;
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 24px;
  font-family: "Trebuchet MS", "Gill Sans", sans-serif;
  color: var(--ink);
  background: radial-gradient(circle at top left, #fff7e6 0%, var(--bg) 45%, #f0ece6 100%);
}}
header {{
  padding: 16px 20px;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 12px;
  box-shadow: 0 8px 20px rgba(0,0,0,0.06);
  margin-bottom: 24px;
}}
section {{
  margin-bottom: 28px;
  padding: 14px 18px;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 12px;
  box-shadow: 0 6px 16px rgba(0,0,0,0.05);
}}
small, .small {{ color: var(--muted); }}
h1 {{ margin: 0 0 6px 0; font-size: 22px; letter-spacing: 0.3px; }}
h2 {{ margin: 10px 0 8px; font-size: 16px; color: var(--accent); }}
table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
th, td {{ padding: 8px 10px; border-bottom: 1px solid var(--border); text-align: left; }}
th {{ text-transform: uppercase; font-size: 11px; letter-spacing: 0.6px; color: var(--muted); }}
tr:nth-child(even) td {{ background: #fbfaf7; }}
</style>
</head>
<body>
<header>
  <h1>Preview Faturas - Agrupado Final</h1>
  <div class="small">Arquivos: Victor = {victor_file} | Larissa = {larissa_file}</div>
</header>
{''.join(f'<section>{s}</section>' for s in sections)}
</body>
</html>
"""
    path.write_text(html, encoding="utf-8")


def main():
    repo_root = _repo_root()
    default_victor = repo_root / "projects" / "data-transactions" / "nubank" / "data" / "input" / "nubankjaneiro26.csv"
    default_larissa = repo_root / "projects" / "data-transactions" / "nubank" / "data" / "input" / "nubankjaneiro26larissa.csv"
    default_output_dir = repo_root / "projects" / "data-transactions" / "nubank" / "reports"

    parser = argparse.ArgumentParser(description="Processa faturas Nubank e gera outputs agregados.")
    parser.add_argument("--victor", default=str(default_victor))
    parser.add_argument("--larissa", default=str(default_larissa))
    parser.add_argument("--output-dir", default=str(default_output_dir))
    parser.add_argument("--prefix", default="jan2026", help="Prefixo para nome dos arquivos de saida")
    parser.add_argument("--html", default="preview_faturas_jan2026.html")
    args = parser.parse_args()

    victor_path = Path(args.victor)
    larissa_path = Path(args.larissa)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    normalize_merchant, load_category_map, get_category, load_model, predict_types = _load_backend()
    category_map = load_category_map()
    model = load_model()

    df_victor = _process_file(victor_path, "Victor", normalize_merchant, category_map, get_category)
    df_larissa = _process_file(larissa_path, "Larissa", normalize_merchant, category_map, get_category)

    df_victor = _assign_type(df_victor, "Victor", predict_types, model)
    df_larissa = _assign_type(df_larissa, "Larissa", predict_types, model)

    final_victor = _final_group(df_victor)
    final_larissa = _final_group(df_larissa)
    final_consolidated = pd.concat([final_victor, final_larissa], ignore_index=True)

    # Save CSVs
    (output_dir / f"resultado_victor_{args.prefix}.csv").write_text(final_victor.to_csv(index=False), encoding="utf-8")
    (output_dir / f"resultado_larissa_{args.prefix}.csv").write_text(final_larissa.to_csv(index=False), encoding="utf-8")
    (output_dir / f"resultado_consolidado_{args.prefix}.csv").write_text(final_consolidated.to_csv(index=False), encoding="utf-8")

    # HTML preview
    html_path = output_dir / args.html
    _render_html(html_path, final_victor, final_larissa, final_consolidated, victor_path.name, larissa_path.name)

    print(f"OK: {html_path}")


if __name__ == "__main__":
    main()
