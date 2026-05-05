import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import sys

import pandas as pd


def find_repo_root(start: Path) -> Path:
    current = start.resolve()
    for parent in [current] + list(current.parents):
        if (parent / "finance-pilot").exists():
            return parent
    return start.resolve()


REPO_ROOT = find_repo_root(Path(__file__).resolve())
BACKEND_DIR = REPO_ROOT / "finance-pilot" / "backend"
REPORTS_DIR = REPO_ROOT / "projects" / "data-transactions" / "nubank" / "reports"

sys.path.insert(0, str(BACKEND_DIR))
from normalization import normalize_merchant  # type: ignore


HTML_PATH = REPORTS_DIR / "category_editor.html"
CATEGORY_MAP_PATH = BACKEND_DIR / "category_map.json"
HISTORY_PATH = REPO_ROOT / "finance-pilot" / "data" / "backups" / "findata_backup_20260202_164435.csv"
HISTORY_CLEAN_PATH = REPO_ROOT / "finance-pilot" / "data" / "backups" / "findata_backup_20260202_164435_clean.csv"

CATEGORIES = [
    "Alimentacao",
    "Transporte",
    "Moradia",
    "Saude",
    "Assinaturas",
    "Compras",
    "Viagem",
    "Educacao",
    "Transferencias",
    "Outros",
]


def load_category_map() -> dict:
    if not CATEGORY_MAP_PATH.exists():
        return {}
    data = json.loads(CATEGORY_MAP_PATH.read_text(encoding="utf-8"))
    return data.get("mapping", {})


def save_category_map(mapping: dict):
    payload = {
        "generated_from": str(HISTORY_PATH),
        "total_keys": len(mapping),
        "mapping": mapping,
    }
    CATEGORY_MAP_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def build_items() -> list[dict]:
    df = pd.read_csv(HISTORY_PATH)
    df["desc_norm"] = df["Observações"].fillna("").astype(str).apply(normalize_merchant)

    counts = (
        df.groupby("desc_norm")
        .size()
        .reset_index(name="qtd")
        .sort_values("qtd", ascending=False)
    )

    examples = (
        df.groupby("desc_norm")["Observações"]
        .apply(lambda x: list(dict.fromkeys(x.dropna().astype(str)))[:3])
        .to_dict()
    )

    mapping = load_category_map()
    items = []
    for _, row in counts.iterrows():
        desc = row["desc_norm"]
        items.append({
            "descricao": desc,
            "categoria": mapping.get(desc, ""),
            "qtd": int(row["qtd"]),
            "exemplos": examples.get(desc, []),
        })

    # include mapping entries not present in history
    for desc, cat in mapping.items():
        if not any(i["descricao"] == desc for i in items):
            items.append({
                "descricao": desc,
                "categoria": cat,
                "qtd": 0,
                "exemplos": [],
            })

    return items


def rebuild_history():
    if not HISTORY_PATH.exists():
        raise FileNotFoundError(f"Historico nao encontrado: {HISTORY_PATH}")

    df = pd.read_csv(HISTORY_PATH)
    mapping = load_category_map()

    df["Observacoes_original"] = df["Observações"]
    df["Grupo_original"] = df["Grupo"]
    df["Observações"] = df["Observações"].fillna("").astype(str).apply(normalize_merchant)
    df["Grupo"] = df["Observações"].map(mapping)
    df["Grupo"] = df["Grupo"].replace({"": pd.NA, "Ambiguo": pd.NA, "Ambígua": pd.NA, "Ambiguous": pd.NA})
    df.loc[df["Grupo"].isna(), "Grupo"] = pd.NA
    df["Review"] = df["Grupo"].isna()

    df.to_csv(HISTORY_CLEAN_PATH, index=False)


class Handler(BaseHTTPRequestHandler):
    def _json(self, data: dict, status: int = 200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/":
            content = HTML_PATH.read_text(encoding="utf-8")
            body = content.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if self.path.startswith("/data"):
            items = build_items()
            self._json({"items": items, "categories": CATEGORIES})
            return

        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length) if length else b"{}"

        if self.path == "/save":
            data = json.loads(body.decode("utf-8"))
            mapping = data.get("mapping", {})
            save_category_map(mapping)
            self._json({"message": f"Salvo: {CATEGORY_MAP_PATH}"})
            return

        if self.path == "/rebuild":
            rebuild_history()
            self._json({"message": f"Historico recriado: {HISTORY_CLEAN_PATH}"})
            return

        self.send_response(404)
        self.end_headers()


def main():
    port = 8010
    server = HTTPServer(("127.0.0.1", port), Handler)
    print(f"Editor ativo em http://127.0.0.1:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
