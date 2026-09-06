import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";
import tseslint from "typescript-eslint";

/**
 * Flat config. Type-aware linting is deliberately off: `npm run typecheck`
 * already runs the compiler over both projects, and running the program twice
 * buys nothing but seconds.
 */
export default tseslint.config(
  {
    ignores: [
      "out/**",
      "release/**",
      "dist/**",
      "node_modules/**",
      "tests/e2e/__screenshots__/**",
      // Build outputs: the composed plugin and the bundled CAD runtime, which
      // carries JavaScript of its own inside site-packages.
      "resources/plugin/**",
      "resources/runtime/**",
      // Vendored, not authored: shadcn/ui and AI Elements are copied in from
      // their registries and re-copied when they are updated. Linting them
      // would mean either reformatting every update or living with noise.
      // They are typechecked, which is the check that matters.
      "src/renderer/components/ui/**",
      "src/renderer/components/ai-elements/**",
      "src/renderer/hooks/use-mobile.ts",
    ],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ["**/*.{ts,tsx,mjs}"],
    languageOptions: {
      ecmaVersion: 2023,
      sourceType: "module",
      globals: { ...globals.node, ...globals.browser, __APP_VERSION__: "readonly" },
    },
    rules: {
      "@typescript-eslint/no-unused-vars": [
        "error",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
      ],
      "@typescript-eslint/consistent-type-imports": [
        "error",
        { prefer: "type-imports", fixStyle: "inline-type-imports" },
      ],
      "no-console": ["warn", { allow: ["warn", "error", "info"] }],
    },
  },
  {
    files: ["src/renderer/**/*.{ts,tsx}"],
    plugins: { "react-hooks": reactHooks },
    rules: reactHooks.configs.recommended.rules,
  },
  {
    // Main talks to a terminal, not a person: console is its output.
    files: ["src/main/**/*.ts", "scripts/**/*.mjs"],
    rules: { "no-console": "off" },
  },
);
