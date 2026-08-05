import { WxPostAuthoringWorkspace } from '@/components/wxpost/authoring/WxPostAuthoringWorkspace';
import { workspaceIdFromEditorKey } from '@/utils/wxpostWorkspace';

export default async function EditWxPostPage({
  params,
  searchParams,
}: {
  params: Promise<{ workspaceKey: string }>;
  searchParams: Promise<{ view?: string }>;
}) {
  const { workspaceKey } = await params;
  const { view } = await searchParams;

  return (
    <WxPostAuthoringWorkspace
      initialWorkspaceId={workspaceIdFromEditorKey(workspaceKey)}
      initialDraftMode={
        view === 'preview' ? 'preview' : view === 'edit' ? 'edit' : undefined
      }
    />
  );
}
