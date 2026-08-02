import { stringify as stringifyYaml } from 'yaml';

import type {
  WxPostArticleDocument,
  WxPostDirectiveNode,
  WxPostMediaAsset,
  WxPostRenderDocument,
} from '../types';
import {
  isWxPostOptionalDirectiveTextPath,
  wxPostDirectiveCollection,
  wxPostDirectiveMediaIds,
} from './directiveRegistry';

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

export type WxPostMediaDeleteTarget = {
  key: string;
  mediaId: string;
};

export class WxPostEditValidationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'WxPostEditValidationError';
  }
}

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

function deleteNestedValue(
  current: unknown,
  path: Array<string | number>
): unknown {
  const [head, ...tail] = path;
  if (head === undefined) return current;
  if (typeof head === 'number') {
    if (!Array.isArray(current) || head < 0 || head >= current.length) {
      throw new Error('Directive edit path does not match an array item.');
    }
    const next = [...current];
    next[head] = deleteNestedValue(next[head], tail);
    return next;
  }
  if (!current || typeof current !== 'object' || Array.isArray(current)) {
    throw new Error('Directive edit path does not match an object field.');
  }
  const record = current as Record<string, unknown>;
  if (!(head in record)) {
    throw new Error(`Directive edit field ${head} does not exist.`);
  }
  if (tail.length === 0) {
    const next = { ...record };
    delete next[head];
    return next;
  }
  return {
    ...record,
    [head]: deleteNestedValue(record[head], tail),
  };
}

function isOptionalDirectiveTextField(
  node: WxPostDirectiveNode,
  path: Array<string | number>
) {
  return isWxPostOptionalDirectiveTextPath(node, path);
}

function directiveItemTarget(
  renderDocument: WxPostRenderDocument,
  key: string
) {
  const target = parseWxPostEditKey(key);
  if (
    target.kind !== 'directive' ||
    target.path.length !== 2 ||
    target.path[0] !== 'items' ||
    typeof target.path[1] !== 'number'
  ) {
    throw new Error('Directive item delete target is invalid.');
  }
  const node = renderDocument.body[target.nodeIndex];
  if (!node || node.kind !== 'directive') {
    throw new Error('Directive item delete target no longer exists.');
  }
  const collection = wxPostDirectiveCollection(node);
  if (!collection || target.path[0] !== collection.definition.path) {
    throw new Error('Directive item delete target no longer exists.');
  }
  if (target.path[1] >= collection.items.length) {
    throw new Error('Directive item delete target is outside its item list.');
  }
  return { target, node, collection, itemIndex: target.path[1] };
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

function directiveSourceRange(bodyMarkdown: string, node: WxPostDirectiveNode) {
  const bodyLines = bodyMarkdown.split('\n');
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
  return {
    openingIndex,
    lineCount: closingIndex - openingIndex + 1,
  };
}

function directiveLines(node: WxPostDirectiveNode) {
  return [
    `:::${node.name}`,
    ...stringifyYaml(node.payload, { lineWidth: 0 }).trimEnd().split('\n'),
    ':::',
  ];
}

export function wxPostBodyMediaIds(renderDocument: WxPostRenderDocument) {
  return new Set(
    renderDocument.body.flatMap((node) =>
      node.kind === 'directive' ? wxPostDirectiveMediaIds(node) : []
    )
  );
}

function orderedMedia(media: WxPostMediaAsset[]) {
  return media.map((item, order) => ({ ...item, order }));
}

export function applyWxPostCoverChange(
  document: WxPostArticleDocument,
  renderDocument: WxPostRenderDocument,
  nextCoverId: string | null,
  newCover?: {
    documentMedia: WxPostMediaAsset;
    renderMedia: WxPostMediaAsset;
  }
) {
  const bodyMediaIds = wxPostBodyMediaIds(renderDocument);
  const previousCoverId = document.coverMediaId ?? null;
  const removePreviousCover =
    previousCoverId !== null &&
    previousCoverId !== nextCoverId &&
    !bodyMediaIds.has(previousCoverId);
  let documentMedia = removePreviousCover
    ? document.media.filter((media) => media.id !== previousCoverId)
    : document.media;
  let renderMedia = removePreviousCover
    ? renderDocument.media.filter((media) => media.id !== previousCoverId)
    : renderDocument.media;

  if (nextCoverId && !documentMedia.some((media) => media.id === nextCoverId)) {
    if (
      !newCover ||
      newCover.documentMedia.id !== nextCoverId ||
      newCover.renderMedia.id !== nextCoverId
    ) {
      throw new Error(
        `Cover image ${nextCoverId} is not available in this Draft.`
      );
    }
    if (
      newCover.documentMedia.kind !== 'image' ||
      newCover.renderMedia.kind !== 'image'
    ) {
      throw new Error('The Draft cover must be an image.');
    }
    documentMedia = [...documentMedia, newCover.documentMedia];
    renderMedia = [...renderMedia, newCover.renderMedia];
  }

  return {
    document: {
      ...document,
      media: orderedMedia(documentMedia),
      coverMediaId: nextCoverId,
    },
    renderDocument: {
      ...renderDocument,
      media: orderedMedia(renderMedia),
      coverMediaId: nextCoverId,
    },
  };
}

/**
 * Remove one explicit media reference from the canonical Draft document.
 * This operates on parsed directive nodes and their source ranges so Draft
 * editing never relies on matching arbitrary Markdown text.
 */
export function applyWxPostMediaDelete(
  document: WxPostArticleDocument,
  renderDocument: WxPostRenderDocument,
  deleteTarget: WxPostMediaDeleteTarget
) {
  const target = parseWxPostEditKey(deleteTarget.key);
  if (target.kind !== 'directive') {
    throw new Error('Draft media delete target is invalid.');
  }
  const nodeIndex = target.nodeIndex;
  const node = renderDocument.body[nodeIndex];
  if (node.kind !== 'directive') {
    throw new Error('Draft media reference is not a directive.');
  }
  const mediaId = deleteTarget.mediaId;
  let galleryItemIndex: number | null = null;
  const directMediaTarget =
    target.path.length === 1 && target.path[0] === 'media';
  let targetMatches = false;
  if (
    node.name === 'gallery' &&
    target.path.length === 2 &&
    target.path[0] === 'items' &&
    typeof target.path[1] === 'number'
  ) {
    galleryItemIndex = target.path[1];
    targetMatches = node.payload.items[galleryItemIndex] === mediaId;
  } else if (
    directMediaTarget &&
    (node.name === 'image' || node.name === 'video' || node.name === 'person')
  ) {
    targetMatches = node.payload.media === mediaId;
  }
  if (!targetMatches) {
    throw new Error(`Draft media ${mediaId} is no longer at this location.`);
  }

  let replacementNode: WxPostDirectiveNode | null;
  if (node.name === 'image' || node.name === 'video') {
    replacementNode = null;
  } else if (node.name === 'gallery') {
    const remaining = node.payload.items.filter(
      (_id, index) => index !== galleryItemIndex
    );
    if (remaining.length > 1) {
      replacementNode = {
        ...node,
        payload: { ...node.payload, items: remaining },
      };
    } else if (remaining.length === 1) {
      replacementNode = {
        kind: 'directive',
        name: 'image',
        line: node.line,
        payload: {
          media: remaining[0],
          ...(node.payload.caption ? { caption: node.payload.caption } : {}),
        },
      };
    } else {
      replacementNode = null;
    }
  } else if (node.name === 'person') {
    const payload = { ...node.payload };
    delete payload.media;
    replacementNode = { ...node, payload };
  } else {
    throw new Error(`Directive ${node.name} does not contain removable media.`);
  }

  const range = directiveSourceRange(document.bodyMarkdown, node);
  const replacementLines = replacementNode
    ? directiveLines(replacementNode)
    : [];
  const lineDelta = replacementLines.length - range.lineCount;
  const nextBody = renderDocument.body.flatMap((item, index) => {
    if (index === nodeIndex) return replacementNode ? [replacementNode] : [];
    if (index > nodeIndex && lineDelta !== 0) {
      return [{ ...item, line: item.line + lineDelta }];
    }
    return [item];
  });
  const keepMedia =
    document.coverMediaId === mediaId ||
    nextBody.some(
      (item) =>
        item.kind === 'directive' &&
        wxPostDirectiveMediaIds(item).includes(mediaId)
    );

  return {
    document: {
      ...document,
      bodyMarkdown: replaceBodyLines(
        document.bodyMarkdown,
        range.openingIndex,
        range.lineCount,
        replacementLines
      ),
      media: keepMedia
        ? document.media
        : document.media.filter((media) => media.id !== mediaId),
      coverMediaId: document.coverMediaId,
    },
    renderDocument: {
      ...renderDocument,
      body: nextBody,
      media: keepMedia
        ? renderDocument.media
        : renderDocument.media.filter((media) => media.id !== mediaId),
      coverMediaId: renderDocument.coverMediaId,
    },
  };
}

export function getWxPostDirectiveItemDeleteDetails(
  renderDocument: WxPostRenderDocument,
  key: string
) {
  const { collection } = directiveItemTarget(renderDocument, key);
  return {
    label: collection.definition.itemLabel,
    removesBlock:
      collection.items.length === collection.definition.minimumItems,
  };
}

export function applyWxPostDirectiveItemDelete(
  document: WxPostArticleDocument,
  renderDocument: WxPostRenderDocument,
  key: string
) {
  const { target, node, collection, itemIndex } = directiveItemTarget(
    renderDocument,
    key
  );
  const remainingItems = collection.items.filter(
    (_item, index) => index !== itemIndex
  );
  const nextNode =
    remainingItems.length > 0
      ? ({
          ...node,
          payload: { ...node.payload, items: remainingItems },
        } as WxPostDirectiveNode)
      : null;
  const range = directiveSourceRange(document.bodyMarkdown, node);
  const replacementLines = nextNode ? directiveLines(nextNode) : [];
  const lineDelta = replacementLines.length - range.lineCount;

  return {
    document: {
      ...document,
      bodyMarkdown: replaceBodyLines(
        document.bodyMarkdown,
        range.openingIndex,
        range.lineCount,
        replacementLines
      ),
    },
    renderDocument: {
      ...renderDocument,
      body: renderDocument.body.flatMap((item, index) => {
        if (index === target.nodeIndex) return nextNode ? [nextNode] : [];
        if (index > target.nodeIndex && lineDelta !== 0) {
          return [{ ...item, line: item.line + lineDelta }];
        }
        return [item];
      }),
    },
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
  const emptyValue = value.trim().length === 0;
  if (emptyValue && !isOptionalDirectiveTextField(node, target.path)) {
    const repeatedItemField =
      target.path.length === 3 &&
      target.path[0] === 'items' &&
      typeof target.path[1] === 'number';
    throw new WxPostEditValidationError(
      repeatedItemField
        ? 'This field cannot be empty. Use Delete item to remove it.'
        : 'This field cannot be empty.'
    );
  }
  const nextPayload = emptyValue
    ? deleteNestedValue(node.payload, target.path)
    : updateNestedValue(node.payload, target.path, value);
  const range = directiveSourceRange(document.bodyMarkdown, node);
  const nextNode = { ...node, payload: nextPayload } as WxPostDirectiveNode;
  const nextDirectiveLines = directiveLines(nextNode);
  const previousLineCount = range.lineCount;
  const lineDelta = nextDirectiveLines.length - previousLineCount;
  return {
    document: {
      ...document,
      bodyMarkdown: replaceBodyLines(
        document.bodyMarkdown,
        range.openingIndex,
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
