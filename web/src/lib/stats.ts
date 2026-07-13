// Probabilidade de cauda calculada NO CLIENTE, para resposta instantânea ao
// mover o slider (sem round-trip à API). Replica fielmente a fórmula de
// stats_empirical.calcular_probabilidade_cauda (Python), assumindo log-retornos
// normais com os parâmetros anualizados.

const DIAS_UTEIS_ANO = 252;

/** Função erro (Abramowitz & Stegun 7.1.26) — precisão ~1e-7. */
function erf(x: number): number {
  const sign = x < 0 ? -1 : 1;
  const ax = Math.abs(x);
  const t = 1 / (1 + 0.3275911 * ax);
  const y =
    1 -
    ((((1.061405429 * t - 1.453152027) * t + 1.421413741) * t - 0.284496736) * t + 0.254829592) *
      t *
      Math.exp(-ax * ax);
  return sign * y;
}

/** CDF da normal padrão Φ(z). */
export function normCdf(z: number): number {
  return 0.5 * (1 + erf(z / Math.SQRT2));
}

export interface TailInput {
  ultimoPreco: number;
  sigmaAnual: number;
  mediaLogAnual: number;
  precoAlvo: number;
  cauda: "inferior" | "superior";
}

export interface TailResult {
  z: number | null;
  probabilidade: number | null;
}

export function probabilidadeCauda(inp: TailInput): TailResult {
  const { ultimoPreco: s0, sigmaAnual, mediaLogAnual, precoAlvo, cauda } = inp;
  const t = 1 / DIAS_UTEIS_ANO;
  const valido =
    Number.isFinite(s0) && s0 > 0 &&
    Number.isFinite(precoAlvo) && precoAlvo > 0 &&
    Number.isFinite(sigmaAnual) && sigmaAnual > 0 &&
    Number.isFinite(mediaLogAnual);
  if (!valido) return { z: null, probabilidade: null };

  const z = (Math.log(precoAlvo / s0) - mediaLogAnual * t) / (sigmaAnual * Math.sqrt(t));
  const prob = cauda === "inferior" ? normCdf(z) : 1 - normCdf(z);
  return { z, probabilidade: prob };
}
