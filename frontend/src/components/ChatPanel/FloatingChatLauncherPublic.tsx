'use client';

import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { Bot, MessageCircle, X } from 'lucide-react';
import { useAuth } from '@/hooks/useAuth';
import { UnifiedChatPanel } from './UnifiedChatPanel';

function generateAgentSessionKeyPublic(): string {
  const id =
    typeof crypto !== 'undefined' && 'randomUUID' in crypto
      ? crypto.randomUUID()
      : Math.random().toString(36).slice(2);
  return `agent-public:web:${id}`;
}

export function FloatingChatLauncherPublic() {
  const { isPending, data: user } = useAuth();
  const [open, setOpen] = useState(false);
  const [agentSessionKey, setAgentSessionKey] = useState<string | null>(null);
  const [mounted, setMounted] = useState(false);

  useEffect(() => setMounted(true), []);

  const onOpen = () => {
    if (!agentSessionKey) {
      setAgentSessionKey(generateAgentSessionKeyPublic());
    }
    setOpen(true);
  };

  if (!mounted || isPending || user) return null;

  const node = (
    <>
      {!open && (
        <button
          type='button'
          onClick={onOpen}
          aria-label='Open public assistant'
          className='fixed bottom-6 right-6 z-50 flex items-center justify-center
                     h-12 w-12 rounded-full
                     bg-indigo-600 hover:bg-indigo-700
                     text-white
                     shadow-lg hover:shadow-xl
                     focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500
                     transition-all'
        >
          <MessageCircle className='w-5 h-5' />
        </button>
      )}
      {agentSessionKey && (
        <div
          role='dialog'
          aria-label='Public Assistant'
          className={`fixed z-50 bg-white border border-gray-200 rounded-xl shadow-2xl
                     flex-col overflow-hidden
                     right-4 bottom-4 w-96 h-[640px] max-h-[calc(100vh-7rem)]
                     max-md:inset-x-2 max-md:w-auto max-md:h-[65vh]
                     ${open ? 'flex' : 'hidden'}`}
        >
          <div className='flex items-center justify-between px-4 py-3 border-b border-gray-200 bg-gray-50'>
            <div className='flex items-center gap-2'>
              <div className='flex items-center justify-center h-6 w-6 rounded-full bg-indigo-100'>
                <Bot className='w-3.5 h-3.5 text-indigo-600' />
              </div>
              <span className='text-sm font-semibold text-gray-900'>
                Public Assistant
              </span>
            </div>
            <button
              type='button'
              onClick={() => setOpen(false)}
              aria-label='Close public assistant'
              className='text-gray-400 hover:text-gray-700 hover:bg-gray-100 rounded-md p-1 transition-colors'
            >
              <X className='w-4 h-4' />
            </button>
          </div>
          <div className='flex-1 min-h-0'>
            <UnifiedChatPanel sessionKey={agentSessionKey} mode='public' />
          </div>
        </div>
      )}
    </>
  );

  return createPortal(node, document.body);
}
