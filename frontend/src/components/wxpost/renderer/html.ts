export function escapeHtml(value: string) {
  return value
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

export function escapeAttribute(value: string) {
  return escapeHtml(value);
}

export function safeUrl(
  value: string | null | undefined,
  options: { allowBlob?: boolean } = {}
) {
  if (!value) return '';
  const allowed = options.allowBlob
    ? /^(?:https?:|blob:)/i
    : /^(?:https?:|mailto:|tel:)/i;
  return allowed.test(value.trim()) ? value.trim() : '';
}

export function inlineStyle(
  declarations: Array<[string, string | number | null | undefined | false]>
) {
  return declarations
    .filter((entry): entry is [string, string | number] =>
      Boolean(entry[1] !== null && entry[1] !== undefined && entry[1] !== false)
    )
    .map(([property, value]) => `${property}:${String(value)}`)
    .join(';');
}

export function styleAttribute(
  declarations: Array<[string, string | number | null | undefined | false]>
) {
  return `style="${escapeAttribute(inlineStyle(declarations))}"`;
}
