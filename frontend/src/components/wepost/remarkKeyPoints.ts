interface MarkdownNode {
  type: string;
  value?: string;
  children?: MarkdownNode[];
  data?: {
    hName?: string;
    hProperties?: {
      className?: string[];
    };
  };
}

const KEY_POINT = /==([^=\n][^=\n]*?)==/g;

function replaceKeyPoints(node: MarkdownNode): void {
  if (!node.children) return;

  node.children = node.children.flatMap((child) => {
    if (child.type !== 'text' || !child.value?.includes('==')) {
      replaceKeyPoints(child);
      return child;
    }

    const replacements: MarkdownNode[] = [];
    let cursor = 0;

    for (const match of child.value.matchAll(KEY_POINT)) {
      const matchIndex = match.index ?? 0;
      if (matchIndex > cursor) {
        replacements.push({
          type: 'text',
          value: child.value.slice(cursor, matchIndex),
        });
      }
      replacements.push({
        type: 'emphasis',
        children: [{ type: 'text', value: match[1] }],
        data: {
          hName: 'span',
          hProperties: {
            className: ['wepost-key-point'],
          },
        },
      });
      cursor = matchIndex + match[0].length;
    }

    if (cursor === 0) return child;
    if (cursor < child.value.length) {
      replacements.push({
        type: 'text',
        value: child.value.slice(cursor),
      });
    }
    return replacements;
  });
}

export function remarkKeyPoints() {
  return (tree: MarkdownNode) => {
    replaceKeyPoints(tree);
  };
}
