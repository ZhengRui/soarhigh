module.exports = {
  // Type check TypeScript files
  '**/*.(ts|tsx)': () => 'tsc --noEmit --emitDeclarationOnly false',

  // Lint & Format TS/JS files
  '**/*.(ts|tsx|js|jsx)': (filenames) => [
    `eslint ${filenames.join(' ')}`,
    `prettier --write ${filenames.join(' ')}`,
  ],

  // Format MD/JSON/YAML files
  '**/*.(md|json|yml|yaml)': (filenames) =>
    `prettier --write ${filenames.join(' ')}`,
};
