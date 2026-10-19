// Money helpers. Amounts travel as whole cents (integers); only display uses decimals.

export function formatMoney(cents: number, currency: string): string {
  try {
    return new Intl.NumberFormat(undefined, { style: 'currency', currency }).format(cents / 100)
  } catch {
    return `${(cents / 100).toFixed(2)} ${currency}`
  }
}

/** "12", "12.5", "12,50", "1,234.56" → cents. Returns null if it isn't a valid amount. */
export function parseAmount(text: string): number | null {
  let t = text.trim().replace(/[^\d.,-]/g, '')
  if (!t) return null
  // A comma followed by exactly 1-2 digits at the end is a decimal comma; other commas are thousands separators.
  if (/,\d{1,2}$/.test(t) && !t.includes('.')) t = t.replace(',', '.')
  t = t.replace(/,/g, '')
  if (!/^-?\d+(\.\d{1,2})?$/.test(t)) return null
  const [whole, frac = ''] = t.split('.')
  const cents = Math.abs(Number(whole)) * 100 + Number((frac + '00').slice(0, 2))
  return (t.startsWith('-') ? -1 : 1) * cents
}

export const CURRENCIES = ['USD', 'EUR', 'GBP', 'INR', 'CAD', 'AUD', 'JPY', 'SGD', 'AED', 'CHF']

export function currencySymbol(currency: string): string {
  try {
    return new Intl.NumberFormat(undefined, { style: 'currency', currency, currencyDisplay: 'narrowSymbol' })
      .formatToParts(0).find((p) => p.type === 'currency')?.value ?? currency
  } catch {
    return currency
  }
}
