export function geciktir<A>(
  f: (a: A) => void,
  ms: number = GECIKME_MS,
  z: Zamanlayici = PENCERE_ZAMANLAYICI,
): Geciktirilmis<A> {
  let kimlik: number | null = null;
  let son: { a: A } | null = null;
  const calistir = () => {
    if (kimlik !== null) z.sil(kimlik);
    kimlik = null;
    const s = son;
    son = null;
    if (s) f(s.a);
  };
  return {
    cagir(a: A) {
      if (kimlik !== null) z.sil(kimlik);
      son = { a };
      kimlik = z.kur(calistir, ms);
    },
    hemen: calistir,
    iptal() {
      if (kimlik !== null) z.sil(kimlik);
      kimlik = null;
      son = null;
    },
    get bekliyor() {
      return son !== null;
    },
  };
}

export class SiraSayaci {
  private son = 0;
  yeni(): number {
    return ++this.son;
  }
  gecerli(s: number): boolean {
    return this.son > 0 && s === this.son;
  }
}
