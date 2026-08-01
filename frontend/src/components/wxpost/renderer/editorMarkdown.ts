function escapeMarkdownText(value: string) {
  return value
    .replaceAll('\\', '\\\\')
    .replace(/([*_`[\]~=])/g, '\\$1')
    .replace(/^([#>+-])(?=\s)/gm, '\\$1')
    .replace(/^(\d+)\.(?=\s)/gm, '$1\\.');
}

function markdownDestination(value: string) {
  if (!/[\s()]/.test(value)) return value;
  return `<${value.replaceAll('\\', '\\\\').replaceAll('>', '\\>')}>`;
}

function markdownTitle(value: string | null) {
  return value
    ? ` "${value.replaceAll('\\', '\\\\').replaceAll('"', '\\"')}"`
    : '';
}

function inlineNode(node: Node): string {
  if (node.nodeType === Node.TEXT_NODE) {
    return escapeMarkdownText(node.textContent ?? '');
  }
  if (!(node instanceof HTMLElement)) return '';
  if (node.dataset.wxpostDecoration === 'true') return '';

  const content = Array.from(node.childNodes).map(inlineNode).join('');
  if (node.classList.contains('wxpost-key-point')) {
    return `==${content}==`;
  }
  switch (node.tagName) {
    case 'BR':
      return '\n';
    case 'STRONG':
    case 'B':
      return `**${content}**`;
    case 'EM':
    case 'I':
      return `*${content}*`;
    case 'DEL':
    case 'S':
      return `~~${content}~~`;
    case 'CODE':
      return `\`${(node.textContent ?? '').replaceAll('`', '\\`')}\``;
    case 'A': {
      const href = node.getAttribute('href');
      return href
        ? `[${content}](${markdownDestination(href)}${markdownTitle(node.getAttribute('title'))})`
        : content;
    }
    case 'IMG': {
      const src = node.getAttribute('src');
      if (!src) return '';
      return `![${escapeMarkdownText(node.getAttribute('alt') ?? '')}](${markdownDestination(src)}${markdownTitle(node.getAttribute('title'))})`;
    }
    case 'INPUT':
      return node.getAttribute('type') === 'checkbox'
        ? `[${node instanceof HTMLInputElement && node.checked ? 'x' : ' '}] `
        : '';
    default:
      return content;
  }
}

function list(element: HTMLElement, ordered: boolean): string {
  const start = ordered ? Number(element.getAttribute('start') ?? '1') : 1;
  const firstNumber = Number.isInteger(start) ? start : 1;
  return Array.from(element.children)
    .filter(
      (child): child is HTMLElement =>
        child instanceof HTMLElement && child.tagName === 'LI'
    )
    .map((item, index) => {
      const nested = Array.from(item.children).filter(
        (child): child is HTMLElement =>
          child instanceof HTMLElement &&
          (child.tagName === 'UL' || child.tagName === 'OL')
      );
      const content = Array.from(item.childNodes)
        .filter(
          (child) =>
            !(
              child instanceof HTMLElement &&
              (child.tagName === 'UL' || child.tagName === 'OL')
            )
        )
        .map(inlineNode)
        .join('')
        .trim();
      const nestedMarkdown = nested
        .map((child) =>
          list(child, child.tagName === 'OL')
            .split('\n')
            .map((line) => `  ${line}`)
            .join('\n')
        )
        .join('\n');
      return `${ordered ? `${firstNumber + index}.` : '-'} ${content}${
        nestedMarkdown ? `\n${nestedMarkdown}` : ''
      }`;
    })
    .join('\n');
}

function table(element: HTMLElement) {
  const rows = Array.from(
    element.querySelectorAll(':scope > thead > tr, :scope > tbody > tr')
  );
  if (rows.length === 0) return '';
  const values = rows.map((row) =>
    Array.from(row.children).map((cell) =>
      Array.from(cell.childNodes).map(inlineNode).join('').trim()
    )
  );
  const width = Math.max(...values.map((row) => row.length));
  const headings = Array.from(
    element.querySelectorAll(':scope > thead > tr:first-child > th')
  );
  const alignment = Array.from({ length: width }, (_, index) => {
    const heading = headings[index] as HTMLElement | undefined;
    return heading?.getAttribute('align') || heading?.style.textAlign || 'left';
  });
  const row = (items: string[]) =>
    `| ${Array.from({ length: width }, (_, index) =>
      (items[index] ?? '').replace(/\|/g, '\\|')
    ).join(' | ')} |`;
  return [
    row(values[0]),
    row(
      alignment.map((value) => {
        if (value === 'center') return ':---:';
        if (value === 'right') return '---:';
        return '---';
      })
    ),
    ...values.slice(1).map(row),
  ].join('\n');
}

function blockNode(node: Node): string {
  if (node.nodeType === Node.TEXT_NODE) {
    return node.textContent?.trim() ? escapeMarkdownText(node.textContent) : '';
  }
  if (!(node instanceof HTMLElement)) return '';
  if (node.dataset.wxpostDecoration === 'true') return '';

  const inline = () =>
    Array.from(node.childNodes).map(inlineNode).join('').trim();
  switch (node.tagName) {
    case 'H2':
      return `## ${inline()}`;
    case 'H3':
      return `### ${inline()}`;
    case 'H4':
      return `#### ${inline()}`;
    case 'H5':
      return `##### ${inline()}`;
    case 'H6':
      return `###### ${inline()}`;
    case 'P':
      return inline();
    case 'UL':
      return list(node, false);
    case 'OL':
      return list(node, true);
    case 'BLOCKQUOTE':
      return Array.from(node.childNodes)
        .map(blockNode)
        .filter(Boolean)
        .join('\n\n')
        .split('\n')
        .map((line) => `> ${line}`)
        .join('\n');
    case 'PRE': {
      const code = node.querySelector('code');
      const language =
        Array.from(code?.classList ?? [])
          .find((name) => name.startsWith('language-'))
          ?.slice('language-'.length) ?? '';
      return `\`\`\`${language}\n${code?.textContent ?? node.textContent ?? ''}\n\`\`\``;
    }
    case 'HR':
      return '---';
    case 'TABLE':
      return table(node);
    default:
      return Array.from(node.childNodes)
        .map(blockNode)
        .filter(Boolean)
        .join('\n\n');
  }
}

export function editableElementToMarkdown(element: HTMLElement) {
  return blockNode(element).trim();
}
