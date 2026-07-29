'use client';

import {
  CalendarDays,
  Edit,
  Files,
  FileText,
  Globe,
  Loader2,
  Lock,
  Newspaper,
  Plus,
  RefreshCw,
} from 'lucide-react';
import Link from 'next/link';
import { useEffect, useRef, useState } from 'react';

import { useAuth } from '@/hooks/useAuth';
import { usePosts } from '@/hooks/usePosts';
import type { ContentKind } from '@/interfaces';

const FILTERS = [
  { value: 'all', label: 'All', icon: Files },
  { value: 'post', label: 'Posts', icon: FileText },
  { value: 'wxpost', label: 'WxPosts', icon: Newspaper },
] satisfies Array<{
  value: ContentKind;
  label: string;
  icon: typeof Files;
}>;

function formatDate(dateString: string) {
  return new Intl.DateTimeFormat('en-US', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  }).format(new Date(dateString));
}

function NewPostMenu() {
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;

    function closeMenu(event: MouseEvent | KeyboardEvent) {
      if (
        event instanceof KeyboardEvent
          ? event.key === 'Escape'
          : !menuRef.current?.contains(event.target as Node)
      ) {
        setOpen(false);
      }
    }

    document.addEventListener('mousedown', closeMenu);
    document.addEventListener('keydown', closeMenu);
    return () => {
      document.removeEventListener('mousedown', closeMenu);
      document.removeEventListener('keydown', closeMenu);
    };
  }, [open]);

  return (
    <div ref={menuRef} className='relative self-start sm:self-center'>
      <button
        type='button'
        className='inline-flex items-center gap-1.5 whitespace-nowrap rounded-md bg-gradient-to-r from-blue-600 to-purple-600 px-3 py-1.5 text-sm text-white shadow-sm transition hover:from-blue-700 hover:to-purple-700 hover:shadow-md'
        aria-expanded={open}
        aria-haspopup='menu'
        data-testid='new-post-menu-trigger'
        onClick={() => setOpen((current) => !current)}
      >
        <Plus className='h-4 w-4' />
        <span className='font-medium'>New Post</span>
      </button>

      {open && (
        <div
          className='absolute left-0 top-full z-30 mt-2 w-44 rounded-lg border border-slate-200 bg-white p-1.5 shadow-lg sm:left-auto sm:right-0'
          role='menu'
          data-testid='new-post-menu'
        >
          <Link
            href='/posts/new'
            className='flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-100 hover:text-slate-950'
            role='menuitem'
          >
            <FileText className='h-4 w-4 text-slate-500' />
            Regular Post
          </Link>
          <Link
            href='/posts/wxposts/new'
            className='flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-100 hover:text-slate-950'
            role='menuitem'
            data-testid='new-wxpost-link'
          >
            <Newspaper className='h-4 w-4 text-slate-500' />
            WeChat Post
          </Link>
        </div>
      )}
    </div>
  );
}

export default function PostsPage() {
  const { data: user } = useAuth();
  const [kind, setKind] = useState<ContentKind>('all');
  const {
    data: content,
    isPending,
    isRefreshingInBackground,
  } = usePosts({
    page: 1,
    pageSize: 10,
    kind,
  });
  const items = content?.items ?? [];

  return (
    <div className='min-h-screen bg-slate-50 py-12'>
      <div className='container mx-auto max-w-4xl px-4'>
        <div className='mb-8 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between'>
          <div>
            <h1 className='mb-2 text-3xl font-bold text-slate-950 sm:mb-4 sm:text-4xl'>
              Posts
            </h1>
            <p className='text-sm text-slate-600 sm:text-base'>
              Stories, meeting notes, and practical ideas from SoarHigh.
            </p>
          </div>

          {user && <NewPostMenu />}
        </div>

        <div
          className='mb-7 grid w-full grid-cols-3 gap-2 rounded-2xl bg-slate-200/60 p-1.5 sm:w-[24rem]'
          aria-label='Content type'
        >
          {FILTERS.map((filter) => {
            const Icon = filter.icon;
            const selected = kind === filter.value;

            return (
              <button
                key={filter.value}
                type='button'
                aria-pressed={selected}
                data-testid={`posts-filter-${filter.value}`}
                className={`group flex min-w-0 items-center justify-center gap-1.5 rounded-xl px-1.5 py-1.5 text-sm font-semibold transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 ${
                  selected
                    ? 'bg-white text-slate-950 shadow-sm ring-1 ring-black/5'
                    : 'text-slate-500 hover:bg-white/60 hover:text-slate-800'
                }`}
                onClick={() => setKind(filter.value)}
              >
                <span
                  className={`grid h-5 w-5 shrink-0 place-items-center rounded-lg transition-all duration-200 ${
                    selected
                      ? 'bg-gradient-to-br from-blue-600 to-purple-600 text-white shadow-sm'
                      : 'bg-white/70 text-slate-400 group-hover:text-slate-600'
                  }`}
                >
                  <Icon className='h-3 w-3' aria-hidden='true' />
                </span>
                <span className='truncate'>{filter.label}</span>
              </button>
            );
          })}
        </div>

        {isPending && !content && (
          <div
            className='grid min-h-[55vh] place-items-center'
            data-testid='posts-loading'
          >
            <Loader2 className='h-8 w-8 animate-spin text-blue-500' />
          </div>
        )}

        {!isPending && items.length === 0 && (
          <div className='grid min-h-[55vh] place-items-center text-center'>
            <p className='text-slate-500'>No content found.</p>
          </div>
        )}

        {items.length > 0 && (
          <div className='space-y-5'>
            {isRefreshingInBackground && (
              <div className='flex items-center justify-center rounded-md bg-blue-50 px-4 py-2'>
                <RefreshCw className='mr-2 h-4 w-4 animate-spin text-blue-500' />
                <span className='text-sm text-blue-600'>
                  Refreshing content…
                </span>
              </div>
            )}

            {items.map((item) => {
              const href =
                item.kind === 'wxpost'
                  ? `/posts/wxposts/${item.slug}`
                  : `/posts/${item.slug}`;

              return (
                <article
                  key={`${item.kind}-${item.id}`}
                  className='overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm transition hover:-translate-y-0.5 hover:shadow-md'
                >
                  <div className='grid sm:grid-cols-[minmax(0,1fr)_10rem]'>
                    <div className='p-5 sm:p-6'>
                      <Link href={href} className='block'>
                        <div className='mb-2 flex flex-wrap items-center gap-2'>
                          {item.kind === 'wxpost' && (
                            <span
                              className='rounded-full bg-gradient-to-r from-blue-600 to-purple-600 px-2.5 py-1 text-[0.68rem] font-semibold uppercase tracking-[0.12em] text-white'
                              data-testid='wxpost-badge'
                            >
                              WxPost
                            </span>
                          )}
                          <h2 className='text-xl font-semibold text-slate-950'>
                            {item.title}
                          </h2>
                        </div>
                        {item.excerpt && (
                          <p className='mt-2 line-clamp-2 text-sm leading-6 text-slate-600'>
                            {item.excerpt}
                          </p>
                        )}
                      </Link>

                      <div className='mt-4 flex flex-wrap items-center gap-3 text-xs text-slate-500'>
                        <span className='flex items-center gap-1'>
                          <CalendarDays className='h-3.5 w-3.5' />
                          {formatDate(item.created_at)}
                        </span>
                        <span>{item.author.name}</span>
                        {item.is_public ? (
                          <span className='inline-flex items-center gap-1 rounded-full bg-green-50 px-2.5 py-1 font-medium text-green-700'>
                            <Globe className='h-3 w-3' />
                            Public
                          </span>
                        ) : (
                          <span className='inline-flex items-center gap-1 rounded-full bg-red-50 px-2.5 py-1 font-medium text-red-700'>
                            <Lock className='h-3 w-3' />
                            Private
                          </span>
                        )}
                        {user && item.kind === 'post' && (
                          <Link
                            href={`/posts/edit/${item.slug}`}
                            className='inline-flex items-center gap-1 rounded-full bg-indigo-50 px-2.5 py-1 font-medium text-indigo-700 transition hover:bg-indigo-100'
                          >
                            <Edit className='h-3.5 w-3.5' />
                            Edit
                          </Link>
                        )}
                      </div>
                    </div>

                    {item.cover_image_url && (
                      <Link
                        href={href}
                        className='order-first block min-h-40 overflow-hidden bg-gradient-to-br from-blue-100 via-slate-100 to-purple-100 sm:order-last'
                        aria-label={`Open ${item.title}`}
                      >
                        <span
                          className='block h-full min-h-40 w-full bg-cover bg-center'
                          style={{
                            backgroundImage: `url("${item.cover_image_url.replaceAll('"', '\\"')}")`,
                          }}
                          aria-hidden='true'
                        />
                      </Link>
                    )}
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
