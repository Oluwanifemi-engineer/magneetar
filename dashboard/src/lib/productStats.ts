/**
 * Single source of truth for the verifiable product stats shown across the
 * public pages (landing hero + login page).
 *
 * These are the ONLY numbers we can back up today (automated test count,
 * real features, real crypto) — deliberately no fabricated adoption stats.
 * Every claim here must stay provable: when the test count changes, update
 * it ONCE here and every page follows. `value`/`prefix`/`suffix` drive the
 * landing hero's animated counters; `display` is the compact form used on
 * the login page.
 */
export interface ProductStat {
  value: number;
  label: string;
  display: string;
  prefix?: string;
  suffix?: string;
}

export const PRODUCT_STATS: ProductStat[] = [
  { value: 381, label: 'automated tests', display: '381' },
  { value: 24, label: 'stealth tracking', suffix: '/7', display: '24/7' },
  { value: 256, label: 'chain-of-custody hashing', prefix: 'SHA-', suffix: '-bit', display: 'SHA-256' },
];
