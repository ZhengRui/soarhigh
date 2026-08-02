import type { WxPostDirectiveName, WxPostDirectiveNode } from '../types';

type DirectivePathPattern = ReadonlyArray<string | '*'>;

interface DirectiveMediaField {
  field: string;
  multiple?: boolean;
}

export interface WxPostDirectiveCollectionDefinition {
  path: 'items';
  itemLabel: string;
  minimumItems: 1;
}

interface WxPostDirectiveDefinition {
  mediaFields: readonly DirectiveMediaField[];
  optionalTextPaths: readonly DirectivePathPattern[];
  collection?: WxPostDirectiveCollectionDefinition;
}

type WxPostDirectiveRegistry = {
  [Name in WxPostDirectiveName]: WxPostDirectiveDefinition;
};

export const WXPOST_DIRECTIVE_REGISTRY = {
  section: {
    mediaFields: [],
    optionalTextPaths: [],
  },
  image: {
    mediaFields: [{ field: 'media' }],
    optionalTextPaths: [['caption']],
  },
  gallery: {
    mediaFields: [{ field: 'items', multiple: true }],
    optionalTextPaths: [['caption']],
  },
  video: {
    mediaFields: [{ field: 'media' }],
    optionalTextPaths: [['caption']],
  },
  takeaway: {
    mediaFields: [],
    optionalTextPaths: [['title']],
  },
  person: {
    mediaFields: [{ field: 'media' }],
    optionalTextPaths: [['role'], ['summary'], ['quote']],
  },
  'info-grid': {
    mediaFields: [],
    optionalTextPaths: [['title']],
    collection: {
      path: 'items',
      itemLabel: 'info item',
      minimumItems: 1,
    },
  },
  timeline: {
    mediaFields: [],
    optionalTextPaths: [['title'], ['items', '*', 'description']],
    collection: {
      path: 'items',
      itemLabel: 'timeline item',
      minimumItems: 1,
    },
  },
  'pull-quote': {
    mediaFields: [],
    optionalTextPaths: [['attribution']],
  },
} as const satisfies WxPostDirectiveRegistry;

function payloadRecord(node: WxPostDirectiveNode) {
  return node.payload as unknown as Record<string, unknown>;
}

export function wxPostDirectiveMediaIds(node: WxPostDirectiveNode) {
  const payload = payloadRecord(node);
  const definition: WxPostDirectiveDefinition =
    WXPOST_DIRECTIVE_REGISTRY[node.name];
  return definition.mediaFields.flatMap((field) => {
    const value = payload[field.field];
    if (field.multiple) {
      return Array.isArray(value)
        ? value.filter((item): item is string => typeof item === 'string')
        : [];
    }
    return typeof value === 'string' ? [value] : [];
  });
}

function pathMatches(
  pattern: DirectivePathPattern,
  path: Array<string | number>
) {
  return (
    pattern.length === path.length &&
    pattern.every(
      (part, index) =>
        part === path[index] ||
        (part === '*' && typeof path[index] === 'number')
    )
  );
}

export function isWxPostOptionalDirectiveTextPath(
  node: WxPostDirectiveNode,
  path: Array<string | number>
) {
  return WXPOST_DIRECTIVE_REGISTRY[node.name].optionalTextPaths.some(
    (pattern) => pathMatches(pattern, path)
  );
}

export function wxPostDirectiveCollection(node: WxPostDirectiveNode) {
  const registryDefinition: WxPostDirectiveDefinition =
    WXPOST_DIRECTIVE_REGISTRY[node.name];
  const collection = registryDefinition.collection;
  if (!collection) return null;
  const items = payloadRecord(node)[collection.path];
  if (!Array.isArray(items)) return null;
  return { definition: collection, items };
}
