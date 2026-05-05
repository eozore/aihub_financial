# Data Transactions - Nubank

Pipeline para consolidar transacoes do Nubank, limpar historico e treinar modelos de classificacao de `Tipo`.

## Estrutura
- `src/`: scripts Python
- `notebooks/`: notebooks historicos
- `data/input/`: CSVs de entrada (export Nubank)
- `data/output/`: artefatos gerados (relatorios, CSVs)
- `data/backup/`: backups locais do historico
- `reports/`: relatorios (HTML)

## Execucao rapida
### Treino de modelo
```
python3 src/train_tipo_model.py \
  --input ../../finance-pilot/data/findata_backup_20260202_164435.csv \
  --output reports/relatorio_modelo_tipo.html
```

### Atualizacao de planilha (legado)
```
python3 src/main.py
```
