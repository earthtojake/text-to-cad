import fs from "node:fs";
import { parse } from "@babel/parser";
import traverseModule from "@babel/traverse";
const traverse = traverseModule.default ?? traverseModule;
for (const file of process.argv.slice(2)) {
  const ast = parse(fs.readFileSync(file, "utf8"), { sourceType: "module", plugins: ["jsx", "typescript"] });
  const dead = [];
  traverse(ast, { Program(path) {
    const walk = (scope) => {
      for (const [name, binding] of Object.entries(scope.bindings)) {
        if (!binding.referenced && !["ImportDefaultSpecifier"].includes(binding.path.type)) {
          dead.push(`${name} (${binding.kind}) line ${binding.path.node.loc.start.line}`);
        }
      }
    };
    walk(path.scope);
    path.traverse({ Function(p) { walk(p.scope); } });
  }});
  if (dead.length) console.log(`${file}\n  ` + dead.join("\n  "));
}
