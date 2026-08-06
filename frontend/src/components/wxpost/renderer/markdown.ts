import type { Root } from 'hast';
import type { Root as MdastRoot } from 'mdast';
import type { Plugin } from 'unified';
import rehypeStringify from 'rehype-stringify';
import remarkGfm from 'remark-gfm';
import remarkParse from 'remark-parse';
import remarkRehype from 'remark-rehype';
import { unified } from 'unified';

import { remarkKeyPoints } from '../remarkKeyPoints';
import type { WxPostLayout } from '../types';
import { wxPostEditKey } from './editing';
import type { PresentationTokens } from './presentation';
import { inlineStyle, safeUrl } from './html';

type HastNode = Root['children'][number] & {
  children?: HastNode[];
  position?: {
    start: { line: number };
    end: { line: number };
  };
  properties?: Record<string, unknown>;
  tagName?: string;
};

interface MarkdownStyleOptions {
  layout: WxPostLayout;
  sectionBody?: boolean;
  sectionHeading?: boolean;
  editable?: {
    nodeIndex: number;
  };
}

function editLabel(tagName: string | undefined) {
  switch (tagName) {
    case 'h2':
    case 'h3':
    case 'h4':
    case 'h5':
    case 'h6':
      return 'section heading';
    case 'p':
      return 'paragraph';
    case 'ul':
    case 'ol':
      return 'list';
    case 'blockquote':
      return 'quote';
    case 'table':
      return 'table';
    case 'pre':
      return 'code block';
    case 'hr':
      return 'divider';
    default:
      return 'draft block';
  }
}

function addEditMetadata(node: HastNode, nodeIndex: number) {
  if (node.type !== 'element' || !node.position) return;
  if (!node.properties) node.properties = {};
  node.properties['data-wxpost-edit-key'] = wxPostEditKey({
    kind: 'markdown',
    nodeIndex,
    startLine: node.position.start.line,
    endLine: node.position.end.line,
  });
  node.properties['data-wxpost-edit-label'] = editLabel(node.tagName);
}

function setStyle(node: HastNode, declarations: Array<[string, string]>) {
  if (!node.properties) node.properties = {};
  const existing =
    typeof node.properties.style === 'string' ? node.properties.style : '';
  node.properties.style = [existing, inlineStyle(declarations)]
    .filter(Boolean)
    .join(';');
}

function styleMarkdown(
  tokens: PresentationTokens,
  options: MarkdownStyleOptions
): Plugin<[], Root> {
  return () => (tree) => {
    const visit = (node: HastNode) => {
      if (node.type === 'element') {
        if (node.properties) {
          if (typeof node.properties.href === 'string') {
            const href = safeUrl(node.properties.href);
            if (href) node.properties.href = href;
            else delete node.properties.href;
          }
          if (typeof node.properties.src === 'string') {
            const src = safeUrl(node.properties.src);
            if (src) node.properties.src = src;
            else delete node.properties.src;
          }
        }
        const classes = Array.isArray(node.properties?.className)
          ? node.properties.className
          : [];
        if (classes.includes('wxpost-key-point')) {
          setStyle(node, [
            ['font-weight', '500'],
            ['text-decoration-line', 'underline'],
            ['text-decoration-color', tokens.accent],
            ['text-decoration-thickness', '2px'],
            ['text-underline-offset', '4px'],
            ['text-decoration-skip-ink', 'none'],
          ]);
        }
        switch (node.tagName) {
          case 'h2':
            setStyle(node, [
              ['margin', '0 0 14px'],
              ['color', tokens.text],
              ['font-family', tokens.titleFont],
              ['font-size', '20px'],
              ['font-weight', '500'],
              ['line-height', '1.35'],
              ['letter-spacing', '-0.02em'],
              ...(options.sectionHeading
                ? []
                : options.layout === 'brand-default'
                  ? ([
                      ['padding', '10px 12px'],
                      ['border-left', `4px solid ${tokens.accent}`],
                      ['border-radius', '0 8px 8px 0'],
                      ['background', tokens.soft],
                    ] as Array<[string, string]>)
                  : options.layout === 'field-notes'
                    ? ([
                        ['padding-bottom', '8px'],
                        ['border-bottom', `1px dashed ${tokens.border}`],
                      ] as Array<[string, string]>)
                    : ([
                        ['padding-top', '10px'],
                        ['border-top', `3px solid ${tokens.accent}`],
                      ] as Array<[string, string]>)),
            ]);
            break;
          case 'h3':
            setStyle(node, [
              ['margin', '0 0 12px'],
              ['color', tokens.text],
              ['font-family', tokens.titleFont],
              ['font-size', '18px'],
              ['font-weight', '500'],
              ['line-height', '1.35'],
              ['letter-spacing', '-0.015em'],
            ]);
            break;
          case 'h4':
          case 'h5':
          case 'h6':
            setStyle(node, [
              ['margin', '0 0 10px'],
              ['color', tokens.text],
              ['font-family', tokens.titleFont],
              ['font-size', '16px'],
              ['font-weight', '600'],
              ['line-height', '1.4'],
            ]);
            break;
          case 'p':
            setStyle(node, [
              ['margin', '0 0 16px'],
              ['color', tokens.text],
            ]);
            break;
          case 'ul':
          case 'ol':
            setStyle(node, [
              ['margin', '0 0 16px'],
              ['padding-left', '24px'],
              ['color', tokens.text],
            ]);
            break;
          case 'li':
            setStyle(node, [['margin', '0 0 6px']]);
            break;
          case 'blockquote':
            setStyle(
              node,
              options.layout === 'editorial-feature'
                ? [
                    ['margin', '0 0 16px'],
                    ['padding', '16px 0'],
                    ['border-top', `1px solid ${tokens.border}`],
                    ['border-bottom', `1px solid ${tokens.border}`],
                    ['color', tokens.text],
                    ['font-family', tokens.titleFont],
                    ['text-align', 'center'],
                  ]
                : [
                    ['margin', '0 0 16px'],
                    ['padding', '14px 16px'],
                    ['border-left', `2px solid ${tokens.accent}`],
                    [
                      'background',
                      options.layout === 'brand-default'
                        ? tokens.soft
                        : 'transparent',
                    ],
                    ['color', tokens.text],
                  ]
            );
            break;
          case 'a':
            setStyle(node, [
              ['color', tokens.accent],
              ['text-decoration', 'underline'],
              ['text-underline-offset', '3px'],
            ]);
            break;
          case 'code':
            setStyle(node, [
              ['padding', '2px 5px'],
              ['background', tokens.soft],
              ['color', tokens.text],
              [
                'font-family',
                'ui-monospace,SFMono-Regular,Menlo,Consolas,monospace',
              ],
              ['font-size', '0.9em'],
            ]);
            break;
          case 'pre':
            setStyle(node, [
              ['margin', '0 0 16px'],
              ['padding', '16px'],
              ['overflow-x', 'auto'],
              ['border', `1px solid ${tokens.border}`],
              ['background', tokens.soft],
            ]);
            break;
          case 'hr':
            setStyle(node, [
              ['margin', '20px 0'],
              ['border', '0'],
              [
                'border-top',
                options.layout === 'brand-default'
                  ? `2px solid ${tokens.accent}`
                  : options.layout === 'field-notes'
                    ? `1px dashed ${tokens.border}`
                    : `1px solid ${tokens.border}`,
              ],
            ]);
            break;
          case 'table':
            setStyle(node, [
              ['width', '100%'],
              ['border-collapse', 'collapse'],
              ['margin', '0 0 16px'],
            ]);
            break;
          case 'th':
          case 'td': {
            const alignment =
              typeof node.properties?.align === 'string'
                ? node.properties.align
                : 'left';
            setStyle(node, [
              ['padding', '8px'],
              ['border-bottom', `1px solid ${tokens.border}`],
              ['text-align', alignment],
              ['vertical-align', 'top'],
              ...(node.tagName === 'th'
                ? ([
                    ['background', tokens.soft],
                    ['color', tokens.accent],
                    ['font-weight', '600'],
                  ] as Array<[string, string]>)
                : []),
            ]);
            break;
          }
        }
        node.children?.forEach(visit);
      }
    };
    tree.children.forEach((node) => visit(node as HastNode));
    if (options.sectionHeading) {
      const heading = tree.children[0] as HastNode | undefined;
      if (heading?.type === 'element' && heading.tagName === 'h2') {
        setStyle(heading, [
          ['min-width', '0'],
          ['margin', '0'],
        ]);
      }
    }
    if (options.sectionBody) {
      tree.children.forEach((child) => {
        const node = child as HastNode;
        if (node.type === 'element') {
          setStyle(node, [['margin', '0']]);
        }
      });
    }
    if (options.editable) {
      tree.children.forEach((child) =>
        addEditMetadata(child as HastNode, options.editable!.nodeIndex)
      );
    }
  };
}

function processor(tokens: PresentationTokens, options: MarkdownStyleOptions) {
  return unified()
    .use(remarkParse)
    .use(remarkGfm)
    .use(remarkKeyPoints)
    .use(remarkRehype)
    .use(styleMarkdown(tokens, options))
    .use(rehypeStringify);
}

export function compileMarkdown(
  source: string,
  tokens: PresentationTokens,
  options: MarkdownStyleOptions
) {
  return String(processor(tokens, options).processSync(source));
}

export function compileSectionMarkdown(
  source: string,
  tokens: PresentationTokens,
  layout: WxPostLayout,
  editable?: MarkdownStyleOptions['editable']
) {
  const parsed = unified().use(remarkParse).parse(source) as MdastRoot;
  const [heading, ...body] = parsed.children;
  const compile = (
    children: MdastRoot['children'],
    options: MarkdownStyleOptions
  ) => {
    const compiler = processor(tokens, options);
    const tree: MdastRoot = { type: 'root', children };
    return String(compiler.stringify(compiler.runSync(tree)));
  };
  return {
    heading: heading
      ? compile([heading], { layout, sectionHeading: true, editable })
      : '',
    body: compile(body, { layout, sectionBody: true, editable }),
  };
}
