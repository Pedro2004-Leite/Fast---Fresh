# Fast & Fresh

Desafio "Fresh eyes on fresh produce": usar as câmaras de teto de uma loja autónoma para detetar, contar e verificar frutas e legumes por gôndola, contra o planograma.
O enunciado está em `dataset/Fruits & Vegetables - Shelf Monitoring Solution.pdf`.

## O que há no repositório

- `crop_planogram.py`: recorta cada área do planograma (crops quadrados de lado fixo, máscara em `.npy`, `dataset.jsonl`).
- `build_sam3_prompts.py` e `classes.json`: os 56 prompts de SAM 3 (um por conceito, com "packaged" para embalados). O resultado é determinístico; o LLM só sugere entradas do dicionário.
- `SAM3/`: cliente e serviço do SAM 3.
- `ui/`: a app de telemóvel (Next.js). É onde se trabalhou mais, e está descrita abaixo.

## Como correr a UI

```bash
cd ui
npm install
npm run dev -- -p 3100
```

- `npm test` (vitest), `npm run lint` e `npx tsc --noEmit` têm de passar antes de dar algo por feito.
- Não corras `npm run build` enquanto o `npm run dev` está ligado na mesma pasta: mistura o `.next` e o CSS deixa de aparecer.
  Se acontecer, pára o servidor, apaga `ui/.next` e arranca outra vez.
- Para ver a app no browser usa `chrome-devtools-axi`, com viewport 390x844 a 2x: `emulate --viewport "390x844x2,mobile,touch"`.
- A pasta `ui/` está ligada a um projeto da Vercel (`fast-and-fresh`, Root Directory `ui`). Cada pessoa tem de correr `vercel link` em `ui/`.
  Não fazer deploy, nem push, sem o dono pedir.

## Como se trabalha na UI

- Cada mudança de UI passa pela skill `lavish`: cria uma página de revisão em `ui/.lavish/` (ignorada pelo git), abre-a e espera o feedback com `lavish-axi poll`.
- Para decisões grandes, primeiro propõe opções no Lavish (com protótipos que se experimentam) e só implementa depois da escolha. Quem decide é o dono do projeto.
- Quando algo no pedido for ambíguo, pergunta ou propõe opções. Já houve três reversões por adivinhar.
- Texto da app em português de Portugal. Nunca usar o travessão longo.
- Lógica pura em `ui/lib/` com testes em `ui/lib/__tests__/`. Componentes em `ui/components/`. Página em `ui/app/page.tsx`.
- Cores só pelos tokens do tema (`ui/app/globals.css`), nunca hexadecimais nos componentes.
- `ui/design/` é o pacote de handoff do Claude Design: só leitura. O design original já foi alterado em vários pontos (ver abaixo).

## Dados

Uma só aplicação com três vistas (Mapa em `/`, Lista em `/lista`, Tarefa em `/tarefa`), ligadas por uma barra em baixo.
O estado é único (`ui/components/AppProvider.tsx`, no layout): leituras, "A tratar" e progresso são partilhados pelas três.

Contrato do desafio, em `ui/lib/types.ts`: cada leitura de uma `area_id` (câmara_nº) tem `stock_level` (`empty`, `half`, `full` ou `null` = sem leitura), `planogram_compliant`, `complaint?` e `minutes_ago`.
A bancada (56 retângulos, uma classe de `classes.json` cada) está em `ui/data/bench-layout.json`.
Hoje os dados são de exemplo (`ui/lib/events.ts`). Para dados reais, troca o corpo de `ui/lib/useEvents.ts`: o resto da app não muda.

## Decisões já tomadas

- **Da Lista para o Mapa**: tocar na parte de cima de um cartão da Lista abre o Mapa com esse aviso selecionado, com a mesma animação de tocar num retângulo (`showOnMap` no `AppProvider`).
- **Vistas**: A (mapa e avisos), B (lista com mini-mapa) e C (próxima tarefa) estão feitas e partilham estado. Barra de navegação de 48 px em baixo.
- **Ecrã A**:

- **Regra de gravidade** (`ui/lib/severity.ts`): produto errado e vazio são críticos (o produto errado vai para o topo); reclamação com metade ou cheio é alto; câmara sem imagem há mais de 30 min dá um aviso médio por câmara; metade ou cheio sem reclamação não dão aviso.
- **Bancada**: 154 px de largura, centrada no mapa de 390 x 480; módulos 1 e 5 horizontais a atravessar a bancada, com a barra de 22 px junto aos módulos 2 e 4 e 4 px de espaço; retângulos `#C4C7C8` e barras `#4A4D50`.
- **"Vou eu" e "Resolvido" são dois passos**: tocar em "Vou eu" e depois deslizar para resolver (trilho a verde). A bola da gravidade viaja até ao retângulo no mapa; resolver é definitivo (não há "Desfazer" em nenhuma vista, tapava o mapa). Os "A tratar" ficam ao atualizar.
- **Atualizar**: botão no cabeçalho, à direita. Traz leituras novas e envelhece as que ficam.
- **Modo Nível**: botão de camadas no cabeçalho. O mapa mostra o enchimento (azul) de cada retângulo; os avisos ficam escondidos no mapa; "sem leitura" às riscas. Abre sempre nos avisos.
- Cores novas fora da gravidade: verde (resolver) e azul (nível).
- **Mapa sozinho (ecrã A)**: só o mapa, a encher o ecrã (até 1,7×), com uma faixa de contador por cima. Tocar num aviso encolhe o mapa e abre a tarefa no sítio da barra de separadores (a barra desce). Fechar: tocar no mapa vazio ou no ×. Filtros e lista estão só na Lista. 
- **Foto da câmara no Mapa**: ao tocar num aviso que tenha foto (`ui/lib/cameraShots.ts`, fotos do dataset em `ui/public/camera/`), o mapa encosta à esquerda (sem o "Tu"), a tarefa fica em baixo e a foto aparece à direita, com o retângulo do planograma a piscar e uma etiqueta do tipo de aviso. Só o "produto errado" tem texto por baixo ("Devia estar aqui: X", o nome do planograma). Tocar na foto amplia-a. Avisos sem foto mantêm o mapa como antes.
- **Dados de demonstração**: o "produto errado" é o lugar 6594_2 (cebolas no lugar da batata vermelha, caso real do dataset). A melancia está certa. Várias etiquetas da app (`class_key`) não coincidem com o produto do planograma (por exemplo Banana é pitaya amarela no planograma); por decidir se o título do aviso passa a usar o nome do planograma.
- **Tarefa (ecrã C)**: só a tarefa atual, num cartão compacto (cerca de 160 px) com "Deslize para resolver" e "Passar" na mesma linha; o mapa aproxima-se à zona do caminho, mas vê sempre pelo menos 322 x 318 px do desenho (para não perder a orientação), e a tarefa cabe em qualquer altura de ecrã (medido de 560 a 844 px). Sem lista "A seguir".

## Ainda por fazer

- Confirmação pela câmara (reabrir o aviso se a câmara ainda vir a prateleira vazia), falso alarme com motivo, prazo no "A tratar" (15 e 30 min), mostrar o que a câmara vê.
- Perguntas em aberto: contorno nas bolas amarela e laranja (contraste baixo), sinal na barra do módulo selecionado, resumo visível depois de atualizar.
- Ligar aos dados reais (SAM 3). O "Arrumar" só sabe que o produto é o errado, não qual está lá.
