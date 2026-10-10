# Alertas de loja autónoma — handoff do design

Pacote de passagem do design (Claude Design) para o código. Ecrãs de telemóvel, **390 × 844**.
Origem: https://claude.ai/artifact/AsFCfS3PxLk3CMMmvRFsLA (privado, só o dono abre), versão publicada **39 (1791656875-297a)**, 10/10/2026.

> Nota sobre formatos: a partir da sessão não consigo ver o menu *Exportar* do editor do Claude Design, por isso
> este pacote foi montado a partir dos ficheiros-fonte do design (`design/source/`) e de renders feitos a partir deles.
> Se o menu *Share › Export* da tua conta oferecer código (React/HTML) ou um bundle para o Claude Code, é um bónus; este pacote já chega para começar.

## O que está aqui

| Pasta | Conteúdo | Para quê |
|---|---|---|
| `design/source/` | `Main.dc.html`, `Lista.dc.html`, `Tarefa.dc.html`, `canvas.json` | Fonte original (só leitura). Cada `.dc.html` tem o HTML (inline styles) e, no fim, a lógica em JS (`renderVals`) com dados, regras e geometria. Não correm fora do Claude Design (precisam do runtime), mas são a fonte da verdade para markup e comportamento. |
| `design/html/` | 1 HTML estático por ecrã | Instantâneo do estado inicial, para ver o markup/CSS já expandido (sem interatividade). |
| `design/png/` | capturas 2× (780×1688) por ecrã e estado + `00-vista-geral.png` | Referência visual para comparar "pixel a pixel". Renderizadas com as fontes reais (Hanken Grotesk e IBM Plex Mono). |
| `design/pdf/ecras.pdf` | 3 páginas, 1 por ecrã | Referência rápida. |
| `tokens/` | `tokens.json`, `tailwind.theme-extend.js`, `icons.json` | Cores, tipografia, raios, espaçamentos, ícones. |
| `data/` | `bench-layout.json`, `events.sample.json`, `classes.json` | Layout da bancada, eventos de exemplo e as 56 classes. |

## Ecrãs e fluxos

- **A · Mapa + avisos** (`Main.dc.html`): cabeçalho (funcionário, ID, loja), planta da bancada de frutas e legumes vista de cima, e por baixo
  um painel com filtros por gravidade (Todos / Crítico / Alto / Médio) e a lista de avisos ordenada por gravidade e depois distância.
  Tocar num retângulo com aviso ou numa linha seleciona-o (toque outra vez para desmarcar). "Vou eu" / "A tratar" alterna por aviso.
- **B · Lista + mini-mapa** (`Lista.dc.html`): lista de cartões; cada cartão traz um mini-mapa (a bancada reduzida e centrada no módulo do aviso),
  a gravidade, o nome, a mensagem, a reclamação, o area_id, a distância e o botão "Vou eu". Ordenar por "Gravidade" ou "Mais perto".
- **C · Próxima tarefa** (`Tarefa.dc.html`): uma tarefa de cada vez. Mapa com o caminho a pontinhos desde "Tu" até ao produto e a distância;
  painel com a gravidade, o produto, o stock, e os botões **Feito** (o produto volta ao normal e o progresso avança) e **Passar** (vai para o fim da fila).
  Lista "A seguir" (tocar numa linha salta para essa tarefa). Estado vazio "Tudo tratado" com "Recomeçar demonstração".

Estados capturados em `design/png/`:
- `A-…__default.png` (A · Mapa + avisos): Estado inicial: nada selecionado, filtro "Todos".
- `A-…__selecionado.png` (A · Mapa + avisos): Aviso selecionado (toque no retângulo ou na linha): contorno no retângulo e faixa do módulo escura.
- `A-…__filtro-critico.png` (A · Mapa + avisos): Filtro "Crítico" na lista (o mapa mostra sempre todos os avisos).
- `B-…__default.png` (B · Lista + mini-mapa): Ordenado por gravidade.
- `B-…__mais-perto.png` (B · Lista + mini-mapa): Ordenado por distância, com um aviso já assumido ("A tratar · tu").
- `C-…__default.png` (C · Próxima tarefa): Primeira tarefa: caminho a pontinhos desde "Tu" e distância.
- `C-…__passar.png` (C · Próxima tarefa): Depois de "Passar": segue para a tarefa seguinte da fila.
- `C-…__feito.png` (C · Próxima tarefa): Depois de "Feito": o produto volta ao normal e a barra de progresso avança.
- `C-…__tudo-tratado.png` (C · Próxima tarefa): Estado vazio: "Tudo tratado".

## Dados (contrato)

A UI recebe, a cada instante, eventos `(area_id, stock_level, complaint?)`:

```ts
type AreaEvent = { area_id: string; stock_level: number /* 0–100 (%) */; complaint?: string | null; minutes_ago?: number };
```

- `area_id` = `<id da câmara>_<n>`, por exemplo `6443_3`. Cada `area_id` corresponde a **um retângulo** da bancada (`data/bench-layout.json`).
- A bancada tem **56 retângulos = as 56 classes de `data/classes.json`**, uma vez cada. O nome mostrado no aviso é o `nome_pt` da classe.
  A ligação classe ↔ câmara ↔ módulo é **inventada para o demo** (14 câmaras do planograma, 4 a 10 retângulos por face).
- **Gravidade** (uma só regra, nos 3 ecrãs):

| Condição | Gravidade |
|---|---|
| `stock_level == 0` | Crítico |
| reclamação **e** `stock_level < 10` | Crítico |
| reclamação **ou** `stock_level < 10` | Alto |
| `stock_level < 25` | Médio |
| restantes | sem aviso |

- Mensagem do aviso: `Repor · stock a X%` se `stock_level < 25`, senão `Verificar · stock a X%`. Sem tratamento especial para stock 0.
- Ordenação padrão: gravidade (decrescente) e depois distância (crescente).
- **Distância a pé**: caminho em ângulos retos desde a posição do utilizador `(60, 240)` no mapa de 390×480. Face A pelo corredor A; face B e
  pontas contornam a ilha pela passagem do topo (y=20) ou do fundo (y=460) e pelo corredor B (x=330); usa o caminho mais curto. 1 px = 0,03 m. Está em `routeOf`/`distOf` na lógica dos `.dc.html` (igual nos 3 ecrãs).
- ID do funcionário `20417`, nome "Pedro" e a loja "Continente Bom Dia São Romão · Leiria" são **fictícios/de exemplo**.

## Bancada (planta)

Tudo em px inteiros, sem linhas nem rebordos: cada produto é um retângulo cinzento (`#D3D5D6`), com **2 px** de intervalo entre retângulos e **4 px** entre módulos.

- Ilha 152×400 centrada no mapa (390×480), com 40 px de passagem no topo e no fundo. 5 módulos: 1 e 5 = pontas (uma só face, 130×60); 2, 3 e 4 = duas faces (A à esquerda, B à direita, 64×88), com o nº do módulo numa faixa de 20 px ao meio.
- Corredor A = fruta, corredor B = legumes, pontas = fruta. Grelhas: A 2×3; B2 2×5; B3 e B4 3×3; ponta 1 2×2; ponta 5 3×2.
- Um retângulo com aviso fica da cor da gravidade (vermelho `#D8322B`, laranja `#F28C1F`, amarelo `#FFD21F`). O crítico pulsa. O selecionado ganha contorno de 2 px em tinta.
- Posições e tamanhos de todas as faces e retângulos: `data/bench-layout.json`.
- Os botões de toque sobre os retângulos são transparentes e têm 44×44 px, centrados no retângulo.

## Notas para a implementação

- Paleta: neutros + tinta carvão `#27282A`. **Sem azul.** Cor só para gravidade. A gravidade também vai por **forma do ícone** (octógono, triângulo, círculo) e por **palavra**, não só por cor.
- Texto: contraste mínimo 4,5:1 (tinta sobre folha 12:1; secundário 6,3:1). O amarelo tem pouco contraste de luminosidade com o cinzento do mapa: destaca-se pela cor.
- Alvos de toque ≥ 44 px. Botões reais (`<button>`), `aria-label` nos retângulos com aviso, `aria-pressed` onde há estado. `prefers-reduced-motion` desliga todas as animações.
- Estado local por ecrã: A (`selected`, `filter`, `claimed`), B (`sort`, `claimed`), C (`done`, `skip`). Em produção, `claimed` e `done` vêm do servidor.
- Fontes: Hanken Grotesk (400–800) e IBM Plex Mono (500, 600) — link do Google Fonts em `tokens/tokens.json`.
- Sugestão de componentes: `Header`, `Bench` (planta; usado em A e C, e em miniatura em B), `SeverityBadge`, `WarningRow`, `WarningCard`, `FilterChips`, `SegmentedControl`, `TaskPanel`, `ProgressSegments`, `RoutePath` (SVG).

## Decisões que ficam contigo

- **Dados reais**: o design só precisa de eventos `(area_id, stock_level, complaint?)`. Em desenvolvimento usa `data/events.sample.json`. Onde corre o SAM 3 / o código Python é uma decisão tua e não faz parte do design.
- **Imagens**: o design **não usa nenhuma imagem** (só SVG inline e CSS), portanto não há nada para alojar na Vercel por causa dele.
- **Páginas**: A, B e C são três direções para o mesmo fluxo; podes manter só uma, ou ter A como principal.

## Ficheiros

```
README.md
data/bench-layout.json
data/classes.json
data/events.sample.json
design/html/A-mapa-avisos.html
design/html/B-lista-minimapa.html
design/html/C-proxima-tarefa.html
design/pdf/ecras.pdf
design/png/00-vista-geral.png
design/png/A-mapa-avisos__default.png
design/png/A-mapa-avisos__filtro-critico.png
design/png/A-mapa-avisos__selecionado.png
design/png/B-lista-minimapa__default.png
design/png/B-lista-minimapa__mais-perto.png
design/png/C-proxima-tarefa__default.png
design/png/C-proxima-tarefa__feito.png
design/png/C-proxima-tarefa__passar.png
design/png/C-proxima-tarefa__tudo-tratado.png
design/source/Lista.dc.html
design/source/Main.dc.html
design/source/Tarefa.dc.html
design/source/canvas.json
tokens/icons.json
tokens/tailwind.theme-extend.js
tokens/tokens.json
```
