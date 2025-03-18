import AgendaExcelGenerator from './AgendaExcelGenerator';
import AgendaExcelPreviewer from './AgendaExcelPreviewer';

export default function ExcelDemoPage() {
  return (
    <div className='container mx-auto p-4'>
      <h1 className='text-2xl font-bold mb-4'>Excel Sheet Demo</h1>
      <AgendaExcelGenerator />
      <AgendaExcelPreviewer autoPreview={true} />
    </div>
  );
}
