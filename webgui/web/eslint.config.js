import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist", "node_modules", "test-results", "playwright-report"] },
  js.configs.recommended,
  ...tseslint.configs.strict,
  reactHooks.configs.flat.recommended,
  {
    languageOptions: { globals: { ...globals.browser } },
    rules: {
      // The browser holds no chess rules and never reaches into the server's code.
      "no-restricted-imports": ["error", { patterns: ["chess.js", "**/server/**", "../../server/*"] }],
    },
  },
  { files: ["*.config.{js,ts}", "e2e/**"], languageOptions: { globals: { ...globals.node } } },
);
