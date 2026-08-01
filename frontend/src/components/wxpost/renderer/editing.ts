import { stringify as stringifyYaml } from 'yaml';

import type {
  WxPostArticleDocument,
  WxPostDirectiveNode,
  WxPostRenderDocument,
} from '../types';

export type WxPostEditTarget =
  | {
      kind: 'article';
      field: 'title' | 'excerpt' | 'byline';
    }
  | {
      kind: 'markdown';
      nodeIndex: number;
      startLine: number;
      endLine: number;
    }
  | {
      kind: 'directive';
      nodeIndex: number;
      path: Array<string | number>;
    }
  | {
      kind: 'media';
      mediaId: string;
      field: 'description';
    };

const KEY_SEPARATOR = '|';

function encodePart(value: string | number) {
  return encodeURIComponent(String(value));
}

function decodePart(value: string) {
  return decodeURIComponent(value);
}

export function wxPostEditKey(target: WxPostEditTarget) {
  switch (target.kind) {
    case 'article':
      return ['article', target.field].map(encodePart).join(KEY_SEPARATOR);
    case 'markdown':
      return ['markdown', target.nodeIndex, target.startLine, target.endLine]
        .map(encodePart)
        .join(KEY_SEPARATOR);
    case 'directive':
      return [
        'directive',
        target.nodeIndex,
        ...target.path.map((part) =>
          typeof part === 'number' ? `#${part}` : part
        ),
      ]
        .map(encodePart)
        .join(KEY_SEPARATOR);
    case 'media':
      return ['media', target.mediaId, target.field]
        .map(encodePart)
        .join(KEY_SEPARATOR);
  }
}

export function parseWxPostEditKey(key: string): WxPostEditTarget {
  const [kind, ...parts] = key.split(KEY_SEPARATOR).map(decodePart);
  if (
    kind === 'article' &&
    parts.length === 1 &&
    (parts[0] === 'title' || parts[0] === 'excerpt' || parts[0] === 'byline')
  ) {
    return { kind, field: parts[0] };
  }
  if (kind === 'markdown' && parts.length === 3) {
    const [nodeIndex, startLine, endLine] = parts.map(Number);
    if (
      [nodeIndex, startLine, endLine].every(Number.isInteger) &&
      nodeIndex >= 0 &&
      startLine > 0 &&
      endLine >= startLine
    ) {
      return { kind, nodeIndex, startLine, endLine };
    }
  }
  if (kind === 'directive' && parts.length >= 2) {
    const nodeIndex = Number(parts[0]);
    if (Number.isInteger(nodeIndex) && nodeIndex >= 0) {
      const path = parts.slice(1).map((part) => {
        if (!part.startsWith('#')) return part;
        const index = Number(part.slice(1));
        if (!Number.isInteger(index) || index < 0) {
          throw new Error(`Invalid WxPost directive array index: ${part}`);
        }
        return index;
      });
      return {
        kind,
        nodeIndex,
        path,
      };
    }
  }
  if (kind === 'media' && parts.length === 2 && parts[1] === 'description') {
    return { kind, mediaId: parts[0], field: parts[1] };
  }
  throw new Error(`Unknown WxPost edit key: ${key}`);
}

function replaceBodyLines(
  bodyMarkdown: string,
  startIndex: number,
  deleteCount: number,
  replacement: string[]
) {
  const lines = bodyMarkdown.split('\n');
  lines.splice(startIndex, deleteCount, ...replacement);
  return lines.join('\n');
}

function updateNestedValue(
  current: unknown,
  path: Array<string | number>,
  value: string
): unknown {
  const [head, ...tail] = path;
  if (head === undefined) return value;
  if (typeof head === 'number') {
    if (!Array.isArray(current) || head < 0 || head >= current.length) {
      throw new Error('Directive edit path does not match an array item.');
    }
    const next = [...current];
    next[head] = updateNestedValue(next[head], tail, value);
    return next;
  }
  if (!current || typeof current !== 'object' || Array.isArray(current)) {
    throw new Error('Directive edit path does not match an object field.');
  }
  const record = current as Record<string, unknown>;
  if (!(head in record)) {
    throw new Error(`Directive edit field ${head} does not exist.`);
  }
  return {
    ...record,
    [head]: updateNestedValue(record[head], tail, value),
  };
}

function updateRenderBodyLines(
  renderDocument: WxPostRenderDocument,
  anchorIndex: number,
  lineDelta: number,
  updateAnchor: (
    node: WxPostRenderDocument['body'][number]
  ) => WxPostRenderDocument['body'][number] | null
) {
  return {
    ...renderDocument,
    body: renderDocument.body.map((node, index) => {
      if (index === anchorIndex) return updateAnchor(node) ?? node;
      if (index > anchorIndex && lineDelta !== 0) {
        return { ...node, line: node.line + lineDelta };
      }
      return node;
    }),
  };
}

export function applyWxPostTextEdit(
  document: WxPostArticleDocument,
  renderDocument: WxPostRenderDocument,
  key: string,
  value: string
) {
  const target = parseWxPostEditKey(key);
  if (target.kind === 'article') {
    const nextValue = target.field === 'title' ? value : value.trim() || null;
    return {
      document: { ...document, [target.field]: nextValue },
      renderDocument: { ...renderDocument, [target.field]: nextValue },
    };
  }

  if (target.kind === 'media') {
    if (
      !document.media.some((media) => media.id === target.mediaId) ||
      !renderDocument.media.some((media) => media.id === target.mediaId)
    ) {
      throw new Error('Media edit target no longer exists.');
    }
    const update = <
      Media extends {
        id: string;
        descriptionSource: 'user' | 'ai';
        descriptionStatus: 'confirmed' | 'needs_confirmation';
      },
    >(
      media: Media
    ) =>
      media.id === target.mediaId
        ? {
            ...media,
            [target.field]: value,
            descriptionSource: 'user' as const,
            descriptionStatus: 'confirmed' as const,
          }
        : media;
    return {
      document: { ...document, media: document.media.map(update) },
      renderDocument: {
        ...renderDocument,
        media: renderDocument.media.map(update),
      },
    };
  }

  if (target.kind === 'markdown') {
    const node = renderDocument.body[target.nodeIndex];
    if (!node || node.kind !== 'markdown') {
      throw new Error('Markdown edit target no longer exists.');
    }
    const sourceLines = node.source.split('\n');
    if (target.endLine > sourceLines.length) {
      throw new Error('Markdown edit range is outside its source node.');
    }
    const replacement = value ? value.split('\n') : [];
    const nextSourceLines = [...sourceLines];
    nextSourceLines.splice(
      target.startLine - 1,
      target.endLine - target.startLine + 1,
      ...replacement
    );
    const nextSource = nextSourceLines.join('\n');
    const lineDelta = nextSourceLines.length - sourceLines.length;
    return {
      document: {
        ...document,
        bodyMarkdown: replaceBodyLines(
          document.bodyMarkdown,
          node.line - 1,
          sourceLines.length,
          nextSourceLines
        ),
      },
      renderDocument: updateRenderBodyLines(
        renderDocument,
        target.nodeIndex,
        lineDelta,
        (item) =>
          item.kind === 'markdown' ? { ...item, source: nextSource } : null
      ),
    };
  }

  const node = renderDocument.body[target.nodeIndex];
  if (!node || node.kind !== 'directive') {
    throw new Error('Directive edit target no longer exists.');
  }
  const nextPayload = updateNestedValue(node.payload, target.path, value);
  const bodyLines = document.bodyMarkdown.split('\n');
  const openingIndex = node.line - 1;
  if (bodyLines[openingIndex]?.trim() !== `:::${node.name}`) {
    throw new Error('Directive source no longer matches its render node.');
  }
  const closingIndex = bodyLines.findIndex(
    (line, index) => index > openingIndex && line.trim() === ':::'
  );
  if (closingIndex < 0) {
    throw new Error('Directive source is missing its closing fence.');
  }
  const nextDirectiveLines = [
    `:::${node.name}`,
    ...stringifyYaml(nextPayload, { lineWidth: 0 }).trimEnd().split('\n'),
    ':::',
  ];
  const previousLineCount = closingIndex - openingIndex + 1;
  const lineDelta = nextDirectiveLines.length - previousLineCount;
  return {
    document: {
      ...document,
      bodyMarkdown: replaceBodyLines(
        document.bodyMarkdown,
        openingIndex,
        previousLineCount,
        nextDirectiveLines
      ),
    },
    renderDocument: updateRenderBodyLines(
      renderDocument,
      target.nodeIndex,
      lineDelta,
      (item) =>
        item.kind === 'directive'
          ? ({
              ...item,
              payload: nextPayload,
            } as WxPostDirectiveNode)
          : null
    ),
  };
}
