import { WxPostAuthoringWorkspace } from '@/components/wxpost/authoring/WxPostAuthoringWorkspace';
import { workspaceIdFromEditorKey } from '@/utils/wxpostWorkspace';

export default async function EditWxPostPage({
  params,
}: {
  params: Promise<{ workspaceKey: string }>;
}) {
  const { workspaceKey } = await params;

  return (
    <WxPostAuthoringWorkspace
      initialWorkspaceId={workspaceIdFromEditorKey(workspaceKey)}
    />
  );
}
