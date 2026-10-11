/**
 * A foto da câmara de cada aviso da demonstração (do dataset do desafio), com o retângulo do planograma
 * (x, y, largura e altura em % da foto) que aponta o sítio do problema, e o produto que o planograma pede aí.
 * Os avisos sem foto aqui continuam a mostrar só o mapa. Em dados reais, a foto e o retângulo vêm do servidor
 * (a câmara do `area_id` e as `image_coordinates` do planograma).
 */
export type Shot = {
  image: string;
  /** Em % da foto; null quando não há zona a apontar (câmara sem imagem). */
  rect: { x: number; y: number; w: number; h: number } | null;
  /** O produto que o planograma pede neste lugar. */
  expected: string | null;
};

export const SHOTS: Record<string, Shot> = {
  "6373_1": { image: "/camera/6373_1.jpg", rect: { x: 25.0, y: 20.58, w: 50.0, h: 31.65 }, expected: "Maçã Gala 70/80" },
  "6462_3": { image: "/camera/6462_3.jpg", rect: { x: 25.0, y: 8.4, w: 50.0, h: 30.26 }, expected: "Manga" },
  "6468_5": { image: "/camera/6468_5.jpg", rect: { x: 31.76, y: 25.0, w: 36.48, h: 50.0 }, expected: "Pitaya amarela 200 g" },
  "6781_3": { image: "/camera/6781_3.jpg", rect: { x: 25.0, y: 39.15, w: 50.0, h: 21.7 }, expected: "Batata vermelha, emb. 3 kg" },
  "6443_3": { image: "/camera/6443_3.jpg", rect: { x: 37.33, y: 38.13, w: 25.34, h: 38.4 }, expected: "Tomate Tasty, emb. 400 g" },
  "6594_2": { image: "/camera/6594_2.jpg", rect: { x: 25.0, y: 29.9, w: 50.0, h: 40.2 }, expected: "Batata vermelha, emb. 5 kg" },
  "6591_3": { image: "/camera/6591_3.jpg", rect: { x: 25.0, y: 29.9, w: 50.0, h: 40.2 }, expected: "Batata Zer0%D, 4 kg" },
  "6376_2": { image: "/camera/6376_2.jpg", rect: { x: 25.0, y: 9.9, w: 50.0, h: 32.28 }, expected: "Meloa Galia" },
  "6594_1": { image: "/camera/6594_1.jpg", rect: { x: 25.0, y: 14.08, w: 50.0, h: 32.86 }, expected: "Abóbora Hokaido" },
  "6383_1": { image: "/camera/6383.jpg", rect: null, expected: null },
};
