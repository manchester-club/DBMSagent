import { useMemo } from 'react';
import Editor from '@monaco-editor/react';

interface CodeViewerProps {
  code: string;
  language?: string;
  height?: string;
}

export function CodeViewer({ code, language = 'json', height = '200px' }: CodeViewerProps) {
  const detectedLanguage = useMemo(() => {
    if (language) return language;
    if (code.trim().startsWith('{') || code.trim().startsWith('[')) return 'json';
    if (code.includes('SELECT') || code.includes('FROM')) return 'sql';
    return 'text';
  }, [code, language]);

  return (
    <div style={{ backgroundColor: '#0a0e27', borderRadius: 4 }}>
      <Editor
        height={height}
        language={detectedLanguage}
        value={code}
        theme="vs-dark"
        options={{
          readOnly: true,
          minimap: { enabled: false },
          scrollBeyondLastLine: false,
          wordWrap: 'on',
          fontSize: 12,
          lineNumbers: 'on',
          renderLineHighlight: 'all',
        }}
      />
    </div>
  );
}
