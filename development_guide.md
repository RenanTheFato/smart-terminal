# Smart Finance — Crypto Terminal (Bybit)

Terminal desktop (Windows/Mac/Linux) para acompanhamento de ativos de criptomoedas em tempo real, usando dados públicos da Bybit. Inspirado nos terminais profissionais de trading (Bloomberg-like), com gráfico, order book, orderflow/footprint, CVD, open interest e TPO.

> Este README funciona como roadmap de desenvolvimento. As fases são sequenciais — cada uma depende da anterior estar minimamente funcional antes de avançar.

---

## Stack

**Já instalado:**
- `pyside6` — interface gráfica (Qt6)
- `qasync` — integra asyncio com o loop de eventos do Qt (necessário pros WebSockets não travarem a UI)
- `pybit` — SDK oficial da Bybit (REST + WebSocket)
- `polars` — processamento de dados de tick/candle
- `numpy` — cálculos numéricos
- `numba` — otimização de funções críticas (footprint, TPO)
- `duckdb` — armazenamento local analítico
- `loguru` — logging

**Faltando adicionar:**
- `pyqtgraph` — plotagem em tempo real (order book, footprint, CVD). É o principal componente visual que ainda falta.
- `pytest` — testes, principalmente da lógica de agregação (CVD, TPO, footprint)

```bash
uv add pyqtgraph
uv add --dev pytest
```

---

## Fase 0 — Fundação do projeto ✅ (feito)

**Objetivo:** ter a aplicação abrindo e confirmando que consegue falar com a API da Bybit.

- [x] Estrutura inicial do projeto com `uv`
- [x] Janela principal em PySide6
- [x] Teste de conexão via `pybit` (endpoint público, sem API key)

---

## Fase 1 — Estrutura do projeto e camada de API

**Objetivo:** organizar o código antes de crescer, e ter um wrapper único de acesso à Bybit que todos os widgets vão consumir.

**O que fazer:**
- Criar a estrutura de pastas (`api/`, `core/`, `ui/`, `storage/`)
- Criar uma classe `BybitClient` (ou similar) que encapsula:
  - Sessão HTTP (`pybit.unified_trading.HTTP`)
  - Conexão WebSocket (`pybit.unified_trading.WebSocket`)
  - Reconexão automática em caso de queda (WS público cai de vez em quando, precisa lidar com isso)
- Decidir e fixar: mercado **linear** (perpétuos USDT) — necessário pra ter Open Interest
- Criar um sistema simples de eventos/sinais (Qt `Signal`/`Slot`) pra distribuir os dados recebidos do WS pros widgets que forem se inscrever, sem acoplar tudo direto na conexão

**Bibliotecas:** `pybit`, `qasync`, `PySide6.QtCore.QObject`/`Signal`

---

## Fase 2 — Camada de armazenamento local

**Objetivo:** ter onde guardar histórico de candles e trades, tanto pra reconstruir gráficos ao abrir o app quanto pra calcular TPO de dias anteriores.

**O que fazer:**
- Definir esquema no DuckDB: tabela de candles (OHLCV por symbol/timeframe) e tabela de trades brutos (symbol, preço, quantidade, lado, timestamp)
- Criar funções de escrita (inserir novos dados recebidos via WS) e leitura (buscar histórico ao iniciar)
- Buscar histórico inicial via REST (`get_kline`) pra popular o banco na primeira execução

**Bibliotecas:** `duckdb`, `polars` (pra transformar resposta da API em DataFrame antes de gravar)

---

## Fase 3 — Gráfico de candlestick

**Objetivo:** primeiro painel visual funcionando, mostrando preço em tempo real.

**O que fazer:**
- Widget de candlestick com `pyqtgraph` (customizando um `GraphicsLayoutWidget` — pyqtgraph não tem candlestick pronto, precisa desenhar via `pg.BarGraphItem` ou item customizado)
- Popular com histórico do DuckDB ao abrir
- Atualizar em tempo real via stream de `kline` do WebSocket
- Seletor de timeframe (1m, 5m, 15m, 1h etc.) e de símbolo (BTCUSDT, ETHUSDT...)

**Bibliotecas:** `pyqtgraph`, `pybit` (stream `kline.{interval}.{symbol}`)

---

## Fase 4 — Order book (livro de ordens)

**Objetivo:** visualização em tempo real da profundidade de mercado.

**O que fazer:**
- Consumir stream `orderbook.{depth}.{symbol}` (a Bybit manda snapshot inicial + deltas — precisa manter o estado local do book e aplicar os deltas corretamente, não só sobrescrever)
- Widget mostrando bids/asks lado a lado ou empilhados, com barra proporcional ao volume em cada nível de preço
- (Opcional, mais pra frente) heatmap de profundidade ao lado do candlestick

**Bibliotecas:** `pyqtgraph`, `pybit`

---

## Fase 5 — Stream de trades (tape) e CVD

**Objetivo:** ter o dado bruto de negociações fluindo, que é a base tanto do CVD quanto do orderflow/footprint.

**O que fazer:**
- Consumir stream `publicTrade.{symbol}`
- Widget simples de "tape" (lista de últimos trades: preço, quantidade, lado, hora)
- Calcular CVD (Cumulative Volume Delta): a cada trade, somar volume se for compra (buyer taker) e subtrair se for venda (seller taker), acumulando ao longo do tempo
- Gráfico de linha do CVD em painel separado, sincronizado no tempo com o candlestick

**Bibliotecas:** `pybit`, `polars`/`numpy` (acumulação), `pyqtgraph` (plot)

---

## Fase 6 — Orderflow / Footprint chart

**Objetivo:** o painel mais complexo — volume negociado por nível de preço, dentro de cada candle, separado por lado comprador/vendedor.

**O que fazer:**
- Agregar os trades da Fase 5 por (candle, nível de preço, lado) — isso é o "footprint" propriamente dito
- Definir o tamanho do bucket de preço (tick size ou agrupamento customizável)
- Desenhar cada candle como uma grade de números (compra x venda) em vez de uma barra simples — isso exige um item gráfico customizado no `pyqtgraph` (ou desenho via `QPainter` direto)
- Marcar visualmente desequilíbrios (imbalance) entre compra/venda em cada nível

**Bibliotecas:** `numba` (a agregação tick a tick pode ficar pesada em Python puro — vale otimizar aqui), `polars`, `pyqtgraph`/`QPainter`

---

## Fase 7 — Open Interest

**Objetivo:** painel de OI, útil pra cruzar com movimento de preço (ex: alta de preço + alta de OI = tendência com força).

**O que fazer:**
- Buscar histórico via REST (`get_open_interest`)
- Atualizar em tempo real via stream `tickers.{symbol}` (que já inclui OI)
- Gráfico de linha simples, sincronizado com o candlestick

**Bibliotecas:** `pybit`, `pyqtgraph`

---

## Fase 8 — TPO (Market Profile)

**Objetivo:** perfil de mercado clássico — distribuição de tempo gasto em cada nível de preço, organizado por período (normalmente sessões de 30min, as "letras" do TPO).

**O que fazer:**
- A partir do histórico de trades/candles no DuckDB, agrupar por período (ex: 30min) e por nível de preço, contando ocorrências (não volume — TPO é sobre *tempo*, diferente do footprint que é sobre *volume*)
- Calcular Value Area (70% do tempo), POC (Point of Control — nível com mais tempo)
- Widget de visualização em "letras"/blocos empilhados horizontalmente por nível de preço

**Bibliotecas:** `polars`, `numpy`, `duckdb` (queries agregadas), `pyqtgraph`/`QPainter`

---

## Fase 9 — Layout de terminal (múltiplos painéis)

**Objetivo:** transformar os widgets isolados em um terminal de verdade, com painéis reorganizáveis.

**O que fazer:**
- Migrar os widgets pra dentro de `QDockWidget`s dentro da `QMainWindow`
- Permitir o usuário arrastar, redimensionar, fechar e reabrir painéis
- Salvar/restaurar o layout entre sessões (Qt tem suporte nativo via `saveState`/`restoreState`)
- Tema visual dark consistente entre todos os painéis

**Bibliotecas:** `PySide6.QtWidgets.QDockWidget`, `PySide6.QtCore.QSettings` (salvar layout e preferências)

---

## Fase 10 — Robustez e testes

**Objetivo:** garantir que a lógica de cálculo (a parte que realmente importa estar certa) não quebra silenciosamente.

**O que fazer:**
- Testes unitários pra CVD, footprint e TPO com dados simulados (não depende de rede)
- Tratamento de reconexão de WebSocket mais robusto (retry com backoff)
- Tratamento de erros de rate limit da API

**Bibliotecas:** `pytest`, `loguru` (pra registrar falhas de conexão/reconexão)

---

## Fase 11 — Empacotamento e distribuição

**Objetivo:** gerar um executável que qualquer pessoa consiga baixar e rodar, sem precisar instalar Python.

**O que fazer:**
- Configurar `PyInstaller` (ou `Briefcase`, se quiser instaladores mais nativos por SO)
- Testar o build nos três sistemas operacionais
- Escrever documentação de instalação e `CONTRIBUTING.md`, já que o plano é deixar open source
- Escolher uma licença (MIT costuma ser a mais comum pra esse tipo de projeto)

**Bibliotecas:** `pyinstaller`

---

## Ordem de dependência entre fases

```
Fase 0 (feito)
   └─ Fase 1 (API layer)
         └─ Fase 2 (storage)
               └─ Fase 3 (candlestick) ──┐
               └─ Fase 4 (order book)    │
               └─ Fase 5 (trades + CVD) ─┤
                     └─ Fase 6 (footprint)
               └─ Fase 7 (open interest) ┤
               └─ Fase 8 (TPO) ──────────┘
                     └─ Fase 9 (layout multi-painel)
                           └─ Fase 10 (testes)
                                 └─ Fase 11 (empacotamento)
```

As fases 3, 4, 5 e 7 podem ser feitas em qualquer ordem entre si (todas dependem só da Fase 1 e 2) — mas footprint (6) precisa da 5, e TPO (8) precisa da 2 já madura com histórico de trades salvo.