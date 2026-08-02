import { expect, test } from '@playwright/test';

import { POST } from '../src/app/api/internal/wxpost/render/route';
import { WXPOST_FIXTURES } from '../src/components/wxpost/fixtures';
import { compileWxPost } from '../src/components/wxpost/renderer/compiler';
import {
  WXPOST_APPEARANCES,
  WXPOST_LAYOUTS,
  WXPOST_PALETTES,
  WXPOST_TYPEFACES,
  type WxPostCompileRequest,
} from '../src/components/wxpost/types';

function request(): WxPostCompileRequest {
  const renderDocument = structuredClone(WXPOST_FIXTURES['meeting-recap']);
  return {
    renderDocument,
    presentation: renderDocument.presentation,
    context: {
      assetUrls: Object.fromEntries(
        renderDocument.media.map((media) => [media.id, media.sourceUrl])
      ),
      contextLabel: 'Meeting 236',
      displayDate: 'July 18, 2026',
      publisherName: 'SoarHigh Toastmasters',
    },
  };
}

test('compiles deterministic self-contained inline HTML for every registered style', () => {
  const input = request();
  const outputs = new Set<string>();

  for (const layout of WXPOST_LAYOUTS) {
    for (const palette of WXPOST_PALETTES) {
      for (const appearance of WXPOST_APPEARANCES) {
        for (const typeface of WXPOST_TYPEFACES) {
          const result = compileWxPost({
            ...input,
            presentation: { layout, palette, appearance, typeface },
          });
          expect(result).toEqual(
            compileWxPost({
              ...input,
              presentation: { layout, palette, appearance, typeface },
            })
          );
          expect(result.html).toContain(`data-layout="${layout}"`);
          expect(result.html).toContain(`data-palette="${palette}"`);
          expect(result.html).toContain(`data-appearance="${appearance}"`);
          expect(result.html).toContain(`data-typeface="${typeface}"`);
          expect(result.html).not.toContain('var(--');
          expect(result.html).not.toContain('display:grid');
          expect(result.html).not.toContain('<script');
          outputs.add(result.html);
        }
      }
    }
  }

  expect(outputs.size).toBe(
    WXPOST_LAYOUTS.length *
      WXPOST_PALETTES.length *
      WXPOST_APPEARANCES.length *
      WXPOST_TYPEFACES.length
  );
});

test('adds explicit source keys only to authoring output', () => {
  const input = request();
  const published = compileWxPost(input).html;
  const authoring = compileWxPost(input, { editable: true }).html;

  expect(published).not.toContain('data-wxpost-edit-key');
  expect(published).not.toContain('data-wxpost-edit-label');
  expect(published).not.toContain('data-wxpost-delete-item');
  for (const label of [
    'draft title',
    'draft excerpt',
    'draft byline',
    'section kicker',
    'section heading',
    'paragraph',
    'image caption',
    'gallery caption',
    'image description',
    'video caption',
    'video description',
    'takeaway title',
    'takeaway text',
    'person name',
    'person role',
    'person summary',
    'person quote',
    'info grid title',
    'info label',
    'info value',
    'timeline title',
    'timeline label',
    'timeline item title',
    'timeline item description',
    'pull quote',
    'quote attribution',
  ]) {
    expect(authoring).toContain(`data-wxpost-edit-label="${label}"`);
  }
  expect(authoring).toContain('data-wxpost-decoration="true"');
  expect(authoring).toContain('data-wxpost-delete-item');
  expect(authoring).toContain('aria-label="Delete info item"');
  expect(authoring).toContain('aria-label="Delete timeline item"');
});

test('omits an absent public date instead of inventing header metadata', () => {
  const input = request();
  delete input.context.displayDate;

  const html = compileWxPost(input).html;

  expect(html).not.toContain('>SoarHigh</span>');
  expect(html).toContain('SoarHigh Toastmasters');
});

test('trusted route returns byte-identical HTML and fails closed', async () => {
  const originalToken = process.env.WXPOST_SERVICE_TOKEN;
  process.env.WXPOST_SERVICE_TOKEN = 'renderer-test-token';
  try {
    const input = request();
    const local = compileWxPost(input);
    const response = await POST(
      new Request('http://localhost/api/internal/wxpost/render', {
        method: 'POST',
        headers: {
          Authorization: 'Bearer renderer-test-token',
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(input),
      })
    );
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual(local);

    const unauthorized = await POST(
      new Request('http://localhost/api/internal/wxpost/render', {
        method: 'POST',
        headers: {
          Authorization: 'Bearer wrong-token',
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(input),
      })
    );
    expect(unauthorized.status).toBe(401);

    const invalid = await POST(
      new Request('http://localhost/api/internal/wxpost/render', {
        method: 'POST',
        headers: {
          Authorization: 'Bearer renderer-test-token',
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ renderDocument: {} }),
      })
    );
    expect(invalid.status).toBe(422);

    const oversized = await POST(
      new Request('http://localhost/api/internal/wxpost/render', {
        method: 'POST',
        headers: {
          Authorization: 'Bearer renderer-test-token',
          'Content-Type': 'application/json',
        },
        body: ' '.repeat(2 * 1024 * 1024 + 1),
      })
    );
    expect(oversized.status).toBe(413);
  } finally {
    if (originalToken === undefined) delete process.env.WXPOST_SERVICE_TOKEN;
    else process.env.WXPOST_SERVICE_TOKEN = originalToken;
  }
});

test('renders all directives, safe markdown, and full-width scrolling galleries', () => {
  const input = request();
  input.renderDocument.body.unshift({
    kind: 'markdown',
    line: 1,
    source:
      '## Safe heading\n\n[unsafe](javascript:alert(1)) <script>alert(1)</script>',
  });
  const html = compileWxPost(input).html;

  for (const directive of [
    'section',
    'image',
    'gallery',
    'video',
    'person',
    'takeaway',
    'info-grid',
    'timeline',
    'pull-quote',
  ]) {
    expect(html).toContain(`data-wxpost-directive="${directive}"`);
  }
  expect(html).not.toContain('javascript:');
  expect(html).not.toContain('<script');
  expect(html).toContain('scroll-snap-type:x mandatory');
  expect(html).toContain('flex:0 0 100%');
  expect(html).not.toContain('aria-label="Previous image"');
  expect(html).not.toContain('aria-label="Next image"');
});

test('renders explicit narrative sections without inferring them from headings', () => {
  const input = request();
  const html = compileWxPost(input).html;

  expect(html).toContain('data-wxpost-directive="section"');
  expect(html).toContain('Opening');
  expect(html).toContain('>01</span>');
  expect(html).toContain('Feedback');
  expect(html).toContain('>02</span>');
  expect(html).toContain('data-wxpost-line="15" data-wxpost-kind="markdown"');
});

test('renders a single image without gallery chrome or duplicate captions', () => {
  const input = request();
  input.renderDocument.body = [
    {
      kind: 'directive',
      name: 'image',
      line: 1,
      payload: {
        media: 'M01',
        caption: 'One meaningful moment from the meeting',
      },
    },
  ];

  const html = compileWxPost(input).html;

  expect(html).toContain('data-wxpost-directive="image"');
  expect(html).toContain('One meaningful moment from the meeting');
  expect(html).not.toContain('>Gallery</span>');
  expect(html).not.toContain('data-testid="gallery-track"');
  expect(html).not.toContain(
    `>${input.renderDocument.media[0].description}</p>`
  );
});
